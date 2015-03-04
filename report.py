#!/usr/bin/python
# -*- coding: utf-8 -*-

import pandas as pd
import psycopg2
import time
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import COMMASPACE, formatdate
from email import encoders
from smtplib import SMTPException
import sys
from json import load as loadjson
from sys import stdin
from pprint import pprint
import csv

SQL_opened_tasks = '''
	select *, 
	(SELECT
		round((severity_name_coefficient * 
		(case
			when source like '%%social%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'social')
			when source like '%%IH%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'IH')
			when source like '%%production%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'production') 
		end) * 
		coalesce(
			(select coverage_percent_coefficient from ext_qa_report_coverage_filter where jira.coverage >= coverage_percent order by coverage_percent desc limit 1)
			, 4))::numeric/10, 2)
		FROM dm_qa_report_jira jira left join ext_qa_report_severity_filter sev on
			jira.severity_name = sev.severity_name
		where jira.issue_key = dm_qa_report_jira.issue_key) as daily_increment,
	(SELECT
		(severity_name_coefficient * 
		(case
			when source like '%%social%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'social')
			when source like '%%IH%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'IH')
			when source like '%%production%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'production') 
		end) * 
		coalesce(
			(select coverage_percent_coefficient from ext_qa_report_coverage_filter where jira.coverage >= coverage_percent order by coverage_percent desc limit 1)
			, 4))
		FROM dm_qa_report_jira jira left join ext_qa_report_severity_filter sev on
			jira.severity_name = sev.severity_name
		where jira.issue_key = dm_qa_report_jira.issue_key) as starting_points,
		now()::date - issue_first_dt as lifetime
 	from dm_qa_report_jira where issue_closed_dt is null'''

SQL_team_stat = '''
	SELECT 
		snap_dt::date,
		team_name,
		points_on_date,
		increment_on_date,
		max_points_on_date,
		limit_exceeded
	FROM dm_qa_report_team_stats where snap_dt = (select max(snap_dt) from dm_qa_report_team_stats)'''

SQL_insert_team_stat = '''
		INSERT INTO dm_qa_report_team_stats(
	            snap_dt, team_name, points_on_date, max_points_on_date, limit_exceeded, 
	            increment_on_date)
	    select 
			now(), 
			t.team, 
			t.points_sum, 
			t.max_points, 
			case 
				when t.points_sum > t.max_points then True 
				else False 
			end, 
			t.daily_increment 
	    from qa_current_team_stat t;'''

SQL_update_points = '''
	UPDATE dm_qa_report_jira main
	SET 
		points = (
		SELECT
			severity_name_coefficient * 
			(case
			when source like '%%social%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'social')
			when source like '%%IH%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'IH')
			when source like '%%production%' then (select source_name_coefficient from ext_qa_report_source_filter where source_name = 'production') 
			end) * 
			coalesce(
			(select coverage_percent_coefficient from ext_qa_report_coverage_filter where jira.coverage >= coverage_percent order by coverage_percent desc limit 1)
			, 4) *
			round((now()::date - issue_first_dt::date)::numeric/10 + 1, 2)
		FROM dm_qa_report_jira jira left join ext_qa_report_severity_filter sev on
			jira.severity_name = sev.severity_name
		where jira.issue_key = main.issue_key)
	WHERE main.issue_closed_dt is null;'''

def transform_file(x):
	x.columns = ['issue_key', 'text', 'issue_link', 'assignee', 'bug', 'issue_status', 'severity_name', 'issue_created_dt', 'components', 'coverage', 'source', 'issue_name']
	x['issue_closed_dt'] = None
	x['issue_first_dt'] = None
	x['points'] = None
	return x

def make_same_col(x):
	x = x[[u'issue_key', u'issue_link', u'assignee', u'issue_status', u'severity_name', u'issue_created_dt', u'components', u'coverage', u'source', u'issue_closed_dt', u'issue_first_dt', u'points', u'issue_name']]
	return x

def insert_new_bugs(new_bug_list, df, conn):
	cursor = conn.cursor()
	for i in new_bug_list:
		SQL = '''
		INSERT INTO dm_qa_report_jira(
			issue_key, 
			issue_link,
			assignee, 
			issue_status,
			severity_name,
			issue_created_dt,
			components,
			coverage,
			source,
			issue_closed_dt,
			issue_first_dt,
			points,
			issue_name)
    	VALUES ('%s',
			'%s',
			'%s',
			'%s',
			'%s', 
            '%s',
            '%s',
            '%s',
            '%s',
            null, 
            '%s',
            null,
            '%s');
		''' % (
		i,
		df.loc[df.issue_key == i, 'issue_link'].values[0],
		df.loc[df.issue_key == i, 'assignee'].values[0],
		df.loc[df.issue_key == i, 'issue_status'].values[0],
		df.loc[df.issue_key == i, 'severity_name'].values[0],
		df.loc[df.issue_key == i, 'issue_created_dt'].values[0],
		df.loc[df.issue_key == i, 'components'].values[0].replace(',',''),
		df.loc[df.issue_key == i, 'coverage'].values[0],
		df.loc[df.issue_key == i, 'source'].values[0],
		time.strftime("%Y-%m-%d"),
		df.loc[df.issue_key == i, 'issue_name'].values[0].replace("'","")
		)
		cursor.execute(SQL)
		conn.commit()

def close_old_bugs(old_bug_list, conn):
	cursor = conn.cursor()
	for ob in old_bug_list:
		SQL = '''
		UPDATE dm_qa_report_jira 
		SET 
			issue_closed_dt = '%s'
		WHERE 
			issue_key = '%s'
		''' % (
			time.strftime("%Y-%m-%d"), 
			ob
		)
		cursor.execute(SQL)
		conn.commit()

def update_bugs(df, conn):
	cursor = conn.cursor()
	for b in df.issue_key:
		SQL = '''
		UPDATE dm_qa_report_jira
		SET
			assignee = '%s',
			issue_status = '%s',
			severity_name = '%s',
			components = '%s',
			coverage = '%s',
			source = '%s',
			issue_name = '%s',
			issue_closed_dt = null
		WHERE 
			issue_key = '%s';
		''' % (
			df.loc[df.issue_key == b, 'assignee'].values[0],
			df.loc[df.issue_key == b, 'issue_status'].values[0],
			df.loc[df.issue_key == b, 'severity_name'].values[0],
			df.loc[df.issue_key == b, 'components'].values[0].replace(',',''),
			str(df.loc[df.issue_key == b, 'coverage'].values[0]).replace(",", "."),
			df.loc[df.issue_key == b, 'source'].values[0],
			df.loc[df.issue_key == b, 'issue_name'].values[0].replace("'",""),
			b
 		)
 		cursor.execute(SQL)
 		conn.commit()

def update_points(conn):
	cursor = conn.cursor()
	cursor.execute(SQL_update_points)
	conn.commit()

def insert_team_stat(conn):
	cursor = conn.cursor()
	cursor.execute(SQL_insert_team_stat)
	conn.commit()

def send_mail(send_from, send_to, subject, text, files=[], server='smtp.uaprom'):
    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime = True)
    msg['Subject'] = subject
    msg.attach( MIMEText(text, 'html') )
    for f in files:
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(f,"rb").read() )
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="{0}"'.format(os.path.basename(f)))
        msg.attach(part)
    smtp = smtplib.SMTP(server)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.quit()

def send_report(flag, conn, email_list=[]):
	today = time.strftime("%Y-%m-%d")

	team_rating = pd.read_sql(SQL_team_stat, conn)
	team_rating.columns = ['Date', 'Team', 'Points', 'Daily Increment', 'Max Points', 'Limit Exceeded Flag']

	opened_issues = pd.read_sql(SQL_opened_tasks, conn)
	opened_issues = opened_issues[['issue_link', 'issue_name', 'assignee', 'issue_status', 'severity_name', 'components', 'coverage', 'source', 'starting_points', 'points', 'daily_increment', 'lifetime']]
	opened_issues.columns = ['Link' , 'Task Name', 'Assignee', 'Status', 'Severity', 'Components', 'Coverage', 'Label', 'Starting Points', 'Points', 'Daily Increment', 'Lifetime']
	opened_issues.sort(['Components', 'Points'], ascending=[True, False], inplace=True)

	emails = pd.read_sql('SELECT * FROM ext_qa_report_email_address', conn)

	if flag == 'all':
		if not email_list:
			recipient_list = emails.loc[emails['component'] == 'all', 'email_address'].values
		else:
			recipient_list = email_list
		send_mail('chuck.norris@smartweb.com.ua', 
			recipient_list, 
			'QA bug report for ' + flag + ': ' + today,
			team_rating.to_html().encode('utf-8') + 
				'''<br>''' + 
				opened_issues.to_html().encode('utf-8')
		)
	elif flag == 'by teams':
		teams = team_rating[['Team']]
		teams.set_index('Team', inplace=True)
		for team in teams.index:
			tmp = opened_issues.loc[opened_issues['Components'].str.contains(team), :].sort(['Points'], ascending=False).reset_index().drop('index', axis=1)
			if not email_list:
				recipient_list = emails.loc[emails['component'] == team, 'email_address'].values
			else:
				recipient_list = email_list
			if team_rating.loc[team_rating['Team'] == team, 'Points'].values[0] > team_rating.loc[team_rating['Team'] == team, 'Max Points'].values[0]:
				warning_text = '<p><strong><font color="red" size="6"> Limit is exceeded by team '+ team + ''' </strong>.</p>.</font>
								<img src="https://kampsportsjov.files.wordpress.com/2013/06/prepare-your-anus.jpg">'''
			else: 
				warning_text = ''
			send_mail('chuck.norris@smartweb.com.ua', 
					recipient_list, 
					'QA bug report for ' + team + ': ' + today, 
					warning_text + 
					team_rating.to_html().encode('utf-8') + 
					'''<br>''' + 
					tmp.to_html().encode('utf-8') , server='smtp.uaprom')

def create_jira_file():
	obj=loadjson(stdin)
	print "Total Open tasks: %d" % obj['total']
	with open('jira.csv', 'wb') as csvfile:
	    spamwriter = csv.writer(csvfile, delimiter=',', quotechar='\"', quoting=csv.QUOTE_ALL)
	    for issue in obj['issues']:
	        components = []
	        for comp in issue['fields']['components']:
	            components.append(comp['name'].encode('utf-8'))
	        percentage = issue['fields'][u'customfield_10590']
	        if percentage == None:
	            percentage = 1
	        spamwriter.writerow([issue['key'].encode('utf-8'),
	            issue['fields'][u'summary'].encode('utf-8'),
	            'http://jira.uaprom/browse/' + issue['key'],
	        	issue['fields']['assignee']['displayName'].encode('utf-8'),
	            issue['fields']['issuetype']['name'].encode('utf-8'),
	            issue['fields']['status']['name'].encode('utf-8'),
	            issue['fields']['priority']['name'].encode('utf-8'),
	            issue['fields']['created'].encode('utf-8'),
	            str(components).replace('[', '').replace(']', '').replace('\'', ''), str(percentage),
	            ', '.join(issue['fields']['labels']).encode('utf-8'),
	        issue['fields']['summary'].encode('utf-8')])

def regular_process(conn, email_list=[]):
	create_jira_file()
	issues_db = pd.read_sql('select * from dm_qa_report_jira', analytics)
	issues_db = make_same_col(issues_db)

	issues_file = pd.read_csv('jira.csv', header = -1)
	os.remove('jira.csv')
	issues_file = transform_file(issues_file)
	issues_file = make_same_col(issues_file)

	new_bugs = [i for i in issues_file.issue_key if i not in issues_db.issue_key.values]
	insert_new_bugs(new_bugs, issues_file, analytics)
	old_bugs = [i for i in issues_db.issue_key if i not in issues_file.issue_key.values]
	close_old_bugs(old_bugs, analytics)


	update_bugs(issues_file, analytics)
	update_points(analytics)
	insert_team_stat(analytics)

	send_report('all', analytics, email_list)
	send_report('by teams', analytics, email_list)



analytics = psycopg2.connect(host = 'db.uaprom', port = '5432', database='qa_report', user='postgres', password = 'postgres')

load_type = sys.argv[1]

if load_type == 'regular':
	test_flag = 0
	regular_process(analytics)
elif load_type == 'report_to_email':
	test_flag = 1
	email_addresses = [sys.argv[2] if len(sys.argv) > 2 else 'Write email addresses. Example: ./qa_report report_to_email chuck.norris@smartweb.com.ua']
	regular_process(analytics, email_addresses)
else:

	sys.exit(1)



