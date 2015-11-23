import sys
import spur
import timeit
import time
import shlex
import os
from docker import Client
import datetime
import glob


_nlines = [1, 50, 100]
_db_name = 'default'
_db_user = 'performance'
_db_pass = ''
_db_port = 5437
_dump = 'performance.sql'
_container = 'performance_yoytec80'
_shell = spur.LocalShell()
_cli = Client(timeout=100)
_pg_badger_path = '/var/lib/postgresql/9.3/main/pg_log'
_output_path = '/tmp'
_odoo_port = 10069


def start_instance(container):
    print 'Start instance'
    exec_id = _cli.exec_create(container, 'supervisorctl start odoo')
    _cli.exec_start(exec_id.get('Id'))


def stop_instance(container):
    print 'Stop instance'
    exec_id = _cli.exec_create(container, 'supervisorctl stop odoo')
    _cli.exec_start(exec_id.get('Id'))


def dropdb(db_name, db_port):
    print 'Drop database'
    dropdb_cmd = 'sudo su postgres -c "dropdb {dbname} -p {port}"'.format(
        dbname=db_name,
        port=db_port)
    _shell.run(shlex.split(dropdb_cmd), allow_error=True)


def load_dump(owner, db_name, db_port, dump_path, pgbadger_path):
    print 'Loading dump'
    create_cmd = \
        'sudo su postgres -c "createdb {dbname} -T template1 -E utf8 -O {owner} -p {port}"'\
        .format(owner=owner, dbname=db_name, port=db_port)
    load_cmd = 'psql {dbname} -f {file_name} -U {owner} -h 127.0.0.1 -p {port}'\
        .format(dbname=db_name, file_name=dump_path, owner=owner, port=db_port)
    os.environ['PGPASSWORD'] = _db_pass
    _shell.run(shlex.split(create_cmd))
    _shell.run(shlex.split(load_cmd))
    remove_logs(pgbadger_path)


def load_process():
    print 'Load process'
    stop_instance(_container)
    dropdb(_db_name, _db_port)
    load_dump(_db_user, _db_name, _db_port, os.path.join(_output_path, _dump), _pg_badger_path)
    start_instance(_container)
    time.sleep(5)


def run_individual_tests():
    print 'Running individual tests (dropdb before creating each sale order)'
    start_time_test = timeit.default_timer()
    for lines in _nlines:
        load_process()
        start_time_test = timeit.default_timer()
        run_test(lines, _db_name, _odoo_port)
        total_time_test = timeit.default_timer() - start_time_test
        print 'Test with {lines} lines: {time}'.format(lines=lines, time=total_time_test)
        run_badger(_pg_badger_path, _output_path, '{}_lines_test'.format(lines))
    total_time_test = timeit.default_timer() - start_time_test
    print 'Test total time: {}'.format(total_time_test)


def run_all_tests():
    load_process()
    print 'Running full tests (load all sale orders without dropping the database)'
    start_time_test = timeit.default_timer()
    for lines in _nlines:
        start_time_test_line = timeit.default_timer()
        run_test(lines, _db_name, _odoo_port)
        total_time_test_line = timeit.default_timer() - start_time_test_line
        print 'Full test with {lines} lines: {time}'.format(lines=lines, time=total_time_test_line)
    total_time_test = timeit.default_timer() - start_time_test
    print 'Full test total time: {}'.format(total_time_test)
    run_badger('/var/lib/postgresql/9.3/main/pg_log', '/tmp', 'all_tests')


def run_test(lines, db_name, odoo_port):
    test_cmd = 'python test_speed.py -l {nlines} -dbo {dbname} -op {port}'.format(
        nlines=lines,
        dbname=db_name,
        port=odoo_port)
    res_test = _shell.run(shlex.split(test_cmd))
    print res_test


def remove_logs(path):
    files = glob.glob(os.path.join(path, '*.log'))
    for f in files:
        print 'Removing {}'.format(f)
        os.remove(f)


def run_badger(in_path, out_path, test_name):
    print 'Running pgbadger'
    date_fmt = datetime.datetime.now().strftime("%Y-%m-%d")
    files = sorted(glob.glob(os.path.join(
        in_path, u'postgresql-*.log')), key=unicode.lower)
    log = files[-1]
    badger_cmd = 'pgbadger -f stderr -s 10 -T "PGBadger: test-{test} {date}" -o {outp}/pgbadger-test-{test}-{date}.html {log_name}'\
        .format(inp=in_path, outp=out_path, date=date_fmt, test=test_name, log_name=log)
    _shell.run(shlex.split(badger_cmd))
    os.rename(log, os.path.join(out_path, os.path.basename(log)))


def main():
    print 'Starting tests...be patient.'
    start_time = timeit.default_timer()
    run_individual_tests()
    run_all_tests()
    end_time = timeit.default_timer()
    total_time = end_time - start_time
    print "Total execution time {}".format(total_time)
    return 0


if __name__ == '__main__':
    sys.exit(main())
