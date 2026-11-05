@echo off
rem Start the Jenkins agent "mark-web-local" under the current Windows user, so builds
rem use this user's Python, Node and Docker Desktop (the Jenkins service runs as LocalSystem).
rem The agent secret is read from %USERPROFILE%\.jenkins-agent-secret (never commit it).
setlocal
set JENKINS_URL=http://localhost:8080
set AGENT_NAME=mark-web-local
set WORKDIR=D:\jenkins-agent
set JAVA="C:\Program Files\Java\jdk-25.0.5+8\bin\java.exe"

if not exist "%WORKDIR%" mkdir "%WORKDIR%"
if not exist "%WORKDIR%\agent.jar" curl -fsS -o "%WORKDIR%\agent.jar" %JENKINS_URL%/jnlpJars/agent.jar || goto :fail
if not exist "%USERPROFILE%\.jenkins-agent-secret" (
  echo Put the agent secret from Jenkins ^(Manage Jenkins ^> Nodes ^> %AGENT_NAME%^) into %USERPROFILE%\.jenkins-agent-secret
  goto :fail
)
%JAVA% -jar "%WORKDIR%\agent.jar" -url %JENKINS_URL%/ -secret @%USERPROFILE%\.jenkins-agent-secret -name %AGENT_NAME% -webSocket -workDir "%WORKDIR%"
goto :eof

:fail
exit /b 1
