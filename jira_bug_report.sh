#!/bin/bash

AUTH="rabbit:rabbit"
API="http://jira.uaprom/rest/api/2"

# что бы отправить отчеты на определенный адрес: ./jira_bug_report.sh report_to_email адрес@получателя.com
# для регулярного запуска: ./jira_bug_report.sh regular 

urlencode () {
         tab="`echo -en "\x9"`"
         i="$@"
         i=${i//%/%25}  ; i=${i//' '/%20} ; i=${i//$tab/%09}
         i=${i//!/%21}  ; i=${i//\"/%22}  ; i=${i//#/%23}
         i=${i//\$/%24} ; i=${i//\&/%26}  ; i=${i//\'/%27}
         i=${i//(/%28}  ; i=${i//)/%29}   ; i=${i//\*/%2a}
         i=${i//+/%2b}  ; i=${i//,/%2c}   ; i=${i//-/%2d}
         i=${i//\./%2e} ; i=${i//\//%2f}  ; i=${i//:/%3a}
         i=${i//;/%3b}  ; i=${i//</%3c}   ; i=${i//=/%3d}
         i=${i//>/%3e}  ; i=${i//\?/%3f}  ; i=${i//@/%40}
         i=${i//\[/%5b} ; i=${i//\\/%5c}  ; i=${i//\]/%5d}
         i=${i//\^/%5e} ; i=${i//_/%5f}   ; i=${i//\`/%60}
         i=${i//\{/%7b} ; i=${i//|/%7c}   ; i=${i//\}/%7d}
         i=${i//\~/%7e} 
         echo "$i"
         i=""
}

SCR_DIR="`readlink -f \`dirname $0\``"

jql=`urlencode  "project = PR AND type = Bug AND component in (customers, commerce, cms, integration, content, procurement) AND labels in ('production') AND status in (\"Ready for dev\", \"In dev\", \"Ready for test\", \"In test\", \"On hold\")"`
curl -s -u $AUTH "$API/search?jql=$jql&fields=key,summary,assignee,issuetype,status,priority,components,created,labels,customfield_10590"  | ${SCR_DIR}/report.py $1 $2
