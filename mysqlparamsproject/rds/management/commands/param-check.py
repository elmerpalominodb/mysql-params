import sys
import logging
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail

from rds.models import CollectorRun, ParameterGroup, DBInstance

logger = logging.getLogger('mysqlparams')

class Command(BaseCommand):

    def handle(self, *args, **options):
        try:
            pg_collector = CollectorRun.objects.get(collector='parameter_group')
            dbi_collector = CollectorRun.objects.get(collector='db_instance')
            pgs = ParameterGroup.objects.filter(run_time=pg_collector.last_run)
            dbis = DBInstance.objects.filter(run_time=dbi_collector.last_run)
            pgs_dict = {}
            dbis_dict = {}
            needs_restart = []
            res = []
            
            new = []
            changed = []
            deleted = []
            for pg in pgs:
                status = pg.status
                if status == 'new':
                    new.append(pg)
                elif status == 'deleted':
                    deleted.append(pg)
                elif status == 'changed':
                    changed.append(pg)
            pgs_dict.update({
                'new':new,
                'deleted':deleted,
                'changed':changed,
            })
            
            new = []
            changed = []
            deleted = []        
            for dbi in dbis:
                status = pg.status
                if status == 'new':
                    new.append(dbi)
                elif status == 'deleted':
                    deleted.append(dbi)
                elif status == 'changed':
                    changed.append(dbi)
                    
            dbis_dict.update({
                'new':new,
                'deleted':deleted,
                'changed':changed,
            })
            
            for dbi in dbis:
                diff = dbi.get_difference_with_pg()
                if len(diff) != 0:
                    needs_restart.append((dbi, diff))
                
            
            if len(pgs_dict.get('new', [])) == 0 and \
                    len(pgs_dict.get('deleted', [])) == 0 and \
                    len(pgs_dict.get('changed', [])) == 0 and \
                    len(dbis_dict.get('new', [])) == 0 and \
                    len(dbis_dict.get('deleted', [])) == 0 and \
                    len(dbis_dict.get('changed', [])) == 0:
               sys.exit(0) 
            
            res.append('Parameter Groups:')
            res.append('')
            res.append('New:')
            new_pgs = pgs_dict.get('new', [])
            if len(new_pgs) == 0:
                res.append('No new parameter groups.')
            else:
                for i,pg in enumerate(new_pgs):
                    res.append('%d. Family: %s Name: %s' % ((i+1), pg.family, pg.name))
            res.append('')
            res.append('Deleted:')
            deleted_pgs = pgs_dict.get('deleted', [])
            if len(deleted_pgs) == 0:
                res.append('No deleted parameter groups.')
            else:
                for i,pg in enumerate(deleted_pgs):
                    res.append('%d. Family: %s Name: %s' % ((i+1), pg.family, pg.name))
            res.append('')
            res.append('Changed:')
            changed_pgs = pgs_dict.get('changed', [])
            if len(changed_pgs) == 0:
                res.append('No changed parameter groups.')
            else:
                for i,pg in enumerate(changed_pgs):
                    prev = ParameterGroup.objects.previous_version(pg)
                    res.append('%d. Family: %s Name: %s' % ((i+1), pg.family, pg.name))
                    res.append('\tOLD ID: %d, NEW ID: %d' % (prev.id, pg.id))
                    res.append('\tChanged Parameters:')
                    changed_params = ParameterGroup.objects.get_changed_parameters(prev, pg)
                    for param in changed_params:
                        res.append("\t- %s: %s -> %s" % (param.get('key'), param.get('old_val'), param.get('new_val')))
            res.append('')            
            
            res.append('DB Instances:')
            res.append('')
            res.append('New:')
            new_dbis = dbis_dict.get('new', [])
            if len(new_dbis) == 0:
                res.append('No new database instances.')
            else:
                for i,dbi in enumerate(new_dbis):
                    res.append('%d. Family: %s Name: %s' % ((i+1), dbi.family, dbi.name))
            res.append('Deleted:')
            deleted_dbis = dbis_dict.get('deleted', [])
            if len(deleted_dbis) == 0:
                res.append('No deleted database instances.')
            else:
                for i,dbi in enumerate(deleted_dbis):
                    res.append('%d. Family: %s Name: %s' % ((i+1), dbi.family, dbi.name))
            res.append('')
            res.append('Changed:')
            changed_dbis = dbis_dict.get('changed', [])
            if len(changed_dbis) == 0:
                res.append('No changed database instances.')
            else:
                for i,dbi in enumerate(changed_dbis):
                    prev = DBInstance.objects.previous_version(dbi)
                    res.append('%d. Region: %s Name: %s Endpoint: %s Port: %s' % ((i+1), dbi.region, dbi.name, dbi.endpoint, dbi.port))
                    res.append('\tOLD ID: %d, NEW ID: %d' % (prev.id, dbi.id))
                    res.append('\tChanged Parameters:')
                    changed_params = DBInstance.objects.get_changed_parameters(prev, dbi)
                    for param in changed_params:
                        res.append("\t- %s: %s -> %s" % (param.get('key'), param.get('old_val'), param.get('new_val')))
            res.append('')
            
            res.append('The following instances may need to be restarted.')
            for dbi_tuple in needs_restart:
                dbi = dbi_tuple[0]
                diff = dbi_tuple[1]
                res.append('%d. Region: %s Name: %s Endpoint: %s Port: %s Parameter Group: %s' % ((i+1), 
                            dbi.region, dbi.name, dbi.endpoint, dbi.port, dbi.parameter_group_name))
                res.append('\tParameter Differences:')
                for param in diff:
                    res.append("\t- %s: Parameter Group Value: %s, DB Instance Value: %s" % (param.get('key'), param.get('pg_val'), param.get('dbi_val')))
            
            subject = '%s Change Alert' % (settings.EMAIL_SUBJECT_PREFIX)
            body = '\n'.join(res)
            from_email = settings.DEFAULT_FROM_EMAIL
            to_emails = []
            for admin in settings.ADMINS:
                to_emails.append(admin[1])
            send_mail(subject, body, from_email, to_emails, fail_silently=False)
        except Exception, e:
            tb = traceback.format_exc()
            logger.error(tb)