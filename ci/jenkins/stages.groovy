def call() {
  env.RELEASE_SHA = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
  currentBuild.description = env.RELEASE_SHA.take(12)
  writeFile file: 'revision.txt', text: env.RELEASE_SHA + '\n'
  def checkMode = params.DEPLOY ? 'release' : 'full'
  try {
    stage(params.DEPLOY ? 'Build and startup check' : 'Full regression and build') {
      timeout(time: 30, unit: 'MINUTES') {
        withEnv(["API_TEST_CHECK_MODE=${checkMode}"]) {
          sh 'bash ci/jenkins/verify-build.sh "$RELEASE_SHA"'
        }
      }
    }
    stage('Publish main') {
      if (params.DEPLOY) {
        // No forced timeout while user jobs are draining.
        if (params.DEPLOY_TARGET == 'cloud-118') {
          sh 'python3 ci/jenkins/release-native.py "$RELEASE_SHA"'
        } else if (!params.DEPLOY_TARGET || params.DEPLOY_TARGET == 'intranet') {
          sh 'python3 ci/jenkins/release.py "$RELEASE_SHA"'
        } else {
          error('Unknown deployment target')
        }
        def releaseStatus = sh(script: '''python3 - <<'PY'
import json
import os
from pathlib import Path
path = Path('.ci-output/release.json')
result = json.loads(path.read_text()) if path.exists() else {}
status = result.get('status') if result.get('revision') == os.environ['RELEASE_SHA'] else None
print(status or 'not-published')
PY''', returnStdout: true).trim()
        currentBuild.description = "${env.RELEASE_SHA.take(12)} · ${releaseStatus}"
        if (releaseStatus == 'postponed') {
          unstable('Release postponed; this build did not publish the candidate. See release.json for the reason.')
        }
      } else {
        echo 'Verification only; current deployment retained.'
      }
    }
  } finally {
    if (checkMode == 'full') {
      junit testResults: '.ci-output/unit.xml', allowEmptyResults: true
    }
    archiveArtifacts artifacts: '.ci-output/*.json,.ci-output/*.txt,revision.txt', allowEmptyArchive: true
  }
}
return this
