import json
import ssl
import urllib.request

# Désactiver la vérification SSL si nécessaire (parfois utile en local)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {"User-Agent": "Mozilla/5.0"}


def check():
    req = urllib.request.Request(
        "https://api.github.com/repos/bambainza/assistantIA-prosartisan/actions/runs",
        headers=headers,
    )
    with urllib.request.urlopen(req, context=ctx) as response:
        data = json.loads(response.read().decode())

    for run in data["workflow_runs"][:3]:
        print(
            f"Run ID: {run['id']}, Commit: {run['head_commit']['message']}, Conclusion: {run['conclusion']}"
        )

        # Obtenir les détails des jobs
        req_jobs = urllib.request.Request(run["jobs_url"], headers=headers)
        with urllib.request.urlopen(req_jobs, context=ctx) as resp_jobs:
            jobs_data = json.loads(resp_jobs.read().decode())

        for job in jobs_data["jobs"]:
            print(f"  Job: {job['name']}, Conclusion: {job['conclusion']}")
            for step in job["steps"]:
                if step["conclusion"] == "failure":
                    print(f"    Failed Step: {step['name']}")
                    # Télécharger les logs du job
                    log_url = f"https://api.github.com/repos/bambainza/assistantIA-prosartisan/actions/jobs/{job['id']}/logs"
                    try:
                        req_logs = urllib.request.Request(log_url, headers=headers)
                        with urllib.request.urlopen(req_logs, context=ctx) as resp_logs:
                            log_content = resp_logs.read().decode("utf-8")
                        print("    --- LOGS (LAST 50 LINES) ---")
                        lines = log_content.splitlines()
                        for line in lines[-50:]:
                            print("      " + line)
                    except Exception as e:
                        print(f"    Could not fetch logs: {e}")


if __name__ == "__main__":
    check()
