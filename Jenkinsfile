// mark-web CI/CD (Windows Jenkins agent).
// CI: Python tests + web build + Docker images. CD: docker compose on this host, then a smoke test.
// Secrets: the .env stays on the agent host (ENV_FILE); it is copied into the workspace only for
// `docker compose up` and deleted afterwards. Never stored in the repo or in Jenkins.
pipeline {
  // Runs on the agent started under the user's Windows account (Python, Node, Docker Desktop).
  agent { label 'mark-web' }

  options {
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
    timeout(time: 45, unit: 'MINUTES')
  }

  parameters {
    booleanParam(name: 'DEPLOY', defaultValue: true, description: 'Run docker compose up and the smoke test after CI')
    booleanParam(name: 'WORKER', defaultValue: false, description: 'Include the background auto-review worker in docker compose build and deploy')
    string(name: 'MARK_WEB_PORT', defaultValue: '8088', description: 'Host port for NGINX')
    string(name: 'MARK_FILES_HOST_DIR', defaultValue: 'D:/CIM Project/mark-web/data/files', description: 'Host folder with the ABS images (git-ignored; mounted read-only)')
    string(name: 'MARK_LOG_HOST_DIR', defaultValue: 'D:/CIM Project/mark-web/logs', description: 'Host folder for persistent API logs')
    string(name: 'ENV_FILE', defaultValue: 'D:/CIM Project/mark-web/.env', description: 'Path of the .env on the agent host')
    string(name: 'PYTHON_EXE', defaultValue: 'python', description: 'Python 3.12 executable (full path if the Jenkins service PATH lacks it)')
  }

  environment {
    COMPOSE_PROJECT_NAME = 'mark-web'
    MARK_WEB_PORT = "${params.MARK_WEB_PORT}"
    MARK_FILES_HOST_DIR = "${params.MARK_FILES_HOST_DIR}"
    MARK_LOG_HOST_DIR = "${params.MARK_LOG_HOST_DIR}"
    PIP_DISABLE_PIP_VERSION_CHECK = '1'
    PYTHON_EXE = "${params.PYTHON_EXE}"
    MARK_ENV_FILE_BS = "${params.ENV_FILE.replace('/', '\\')}"
  }

  stages {
    stage('Preflight') {
      steps {
        bat '"%PYTHON_EXE%" --version && node --version && git --version && docker version --format "docker {{.Server.Version}}"'
      }
    }

    stage('Python tests') {
      steps {
        bat '"%PYTHON_EXE%" -m venv .venv'
        bat '.venv\\Scripts\\python -m pip install -q -e ".[dev,api]"'
        // separate steps: in cmd, `if not exist X a && b` runs b only inside the if
        bat 'if exist reports rmdir /S /Q reports'
        // tests/regression reads artifacts/ (customer data, git-ignored): it is a local gate, not run in CI
        bat '.venv\\Scripts\\python -m pytest tests -q --ignore=tests/regression --junitxml=reports\\pytest.xml'
      }
      post {
        always { junit allowEmptyResults: false, testResults: 'reports/pytest.xml' }
      }
    }

    stage('Web build') {
      steps {
        dir('web') {
          bat 'npm ci --no-audit --no-fund'
          bat 'npm run build'
        }
      }
    }

    stage('Docker images') {
      steps {
        script {
          if (params.WORKER) {
            bat 'docker compose --profile worker build'
          } else {
            bat 'docker compose build'
          }
        }
      }
    }

    stage('Deploy') {
      when { expression { params.DEPLOY } }
      steps {
        // cmd `copy` rejects forward slashes in the source path
        withEnv(["MARK_ENV_FILE=${params.ENV_FILE.replace('/', '\\')}"]) {
          bat 'if not exist "%MARK_ENV_FILE%" (echo ENV_FILE not found: %MARK_ENV_FILE% & exit /b 1)'
          bat 'copy /Y "%MARK_ENV_FILE%" .env >nul'
          script {
            if (params.WORKER) {
              bat 'docker compose --profile worker up -d --remove-orphans'
            } else {
              bat 'docker compose up -d --remove-orphans'
            }
          }
        }
      }
      post {
        always { bat 'if exist .env del /Q .env' }
      }
    }

    stage('Smoke test') {
      when { expression { params.DEPLOY } }
      steps {
        // /api/ready checks the DB and the image folder; the headers prove NGINX config is live.
        powershell '''
          $base = "http://localhost:$env:MARK_WEB_PORT"
          $ok = $false
          foreach ($i in 1..30) {
            try { if ((Invoke-WebRequest "$base/api/ready" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { $ok = $true; break } } catch {}
            Start-Sleep -Seconds 2
          }
          if (-not $ok) { docker compose logs --tail 50 api; throw "api not ready at $base" }
          try { Invoke-WebRequest "$base/api/runs" -UseBasicParsing | Out-Null } catch { $r = $_.Exception.Response }
          if ([int]$r.StatusCode -ne 401) { throw "expected 401 without login, got $([int]$r.StatusCode)" }
          if ($r.Headers["Cache-Control"] -ne "no-store" -or -not $r.Headers["Content-Security-Policy"]) { throw "security headers missing on /api" }
          Write-Host "smoke OK: $base"
        '''
      }
    }

    stage('Real-DB check') {
      when { expression { params.DEPLOY } }
      steps {
        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
          bat '.venv\\Scripts\\python scripts\\check_trial_readonly.py --run 19 --env-file "%MARK_ENV_FILE_BS%"'
        }
      }
    }
  }

  post {
    failure { bat 'docker compose ps' }
  }
}
