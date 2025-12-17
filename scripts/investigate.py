import os 
import sys 
import json 
import requests 
from openai import OpenAI
from slack_sdk import WebClient


slack_webhook_url = os.getenv("SLACK_WEBHOOK")

def investigate_logs(log_file_path):
    # READ LOGS FROM FILE
    if not os.path.exists(log_file_path):
        return "File does not exist"
    with open(log_file_path, 'r') as file:
        logs = file.readlines()
        tail_logs = "".join(logs[-100:])

    # Metadata for GitHub Environment
    workflow_name = os.getenv("GITHUB_WORKFLOW_NAME")
    job_name = os.getenv("GITHUB_JOB_NAME")
    repository = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("GITHUB_RUN_ID")
    
    # ASK AI TO INVESTIGATE
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    system_prompt = """
    You are a senior DevOps engineer performing automated CI/CD failure triage for GitHub Actions workflows.
    You will be given GitHub Actions job logs (possibly truncated) and workflow metadata.
    Your objective is to minimize investigation time for the on-call engineer.
    
    Strict rules:
    - Identify the earliest *actionable* failure in execution order.
    - Ignore secondary, cascading, or cleanup errors.
    - Do NOT speculate beyond what is present in the logs.
    - If the logs do not contain a concrete root error, state this explicitly.
    - Prefer accuracy and clarity over completeness.
    """
    user_prompt = f"""
    Strict rules:
    - Identify the earliest *actionable* failure in execution order.
    - Ignore secondary, cascading, or cleanup errors.
    - Do NOT speculate beyond what is present in the logs.
    - If the logs do not contain a concrete root error, state this explicitly.
    - Prefer accuracy and clarity over completeness.

    Metadata:
    - Workflow: {workflow_name}
    - Job: {job_name}
    - Run URL: https://github.com/{repository}/actions/runs/{run_id}
    Tasks:

    1. Identify the earliest failure:
    - Quote the exact log line(s) that indicate the failure.
    - If only generic messages are present (e.g., "Process completed with exit code 1"), state that no actionable root error is visible.

    2. Localize where the failure occurred:
    - Workflow name
    - Job name
    - Step name (or action name)
    - `run:` command or action being executed
    - File path, line number, container, or Kubernetes pod (if present)
    - If localization is incomplete, explicitly state why.

    3. Classify the failure into exactly ONE category:
    infra | dependency | auth | config | test | timeout

    4. Assign a confidence level:
    - High: clear root error and precise location
    - Medium: strong signal but missing some context
    - Low: generic failure or insufficient logs

    5. Summarize the likely root cause in 1–2 sentences.
    - If confidence is Low, describe the most probable failure class without guessing specifics.

    6. Provide 2–4 fast verification or remediation steps:
    - Steps must be concrete and immediately actionable.
    - Prefer validation commands or checks over permanent fixes.
    - Avoid generic advice.

    Output format (Slack-ready, exact):
    ---
    🚨 *Pipeline Failure Detected*

    *Failure Category:* <category>
    *Confidence:* <High | Medium | Low>

    *Earliest Failure:*
    <quoted error or explicit statement that no actionable error is present>

    *Location:*
    - Repository: {repository}
    - Workflow: {workflow_name}
    - Job: {job_name}

    *Root Cause Assessment:*
    <concise explanation>

    *Recommended Next Steps:*
    1. <step>
    2. <step>
    3. <step>

    *Run URL:* https://github.com/{repository}/actions/runs/{run_id}
    ---

    Do NOT include raw logs.
    Do NOT add commentary outside this format.

    """
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    return response.choices[0].message.content

def send_to_slack(slack_webhook_url, message, run_url):
    # Send Report to Slack
    if not slack_webhook_url:
        raise ValueError("SLACK_WEBHOOK environment variable is not set")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚨 *CI/CD Failure Analysis* 🚨",
                "emoji": True
            }, 
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{message}"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Failed Run",
                        "emoji": True
                    },
                    "url": run_url,
                    "style": "danger"
                }
            ]
        }
    ]
    payload = {"blocks": blocks}
    response = requests.post(slack_webhook_url, json=payload)
    if response.status_code != 200:
        raise Exception("Failed to send Slack notification")
    print("Slack notification sent successfully")

if __name__ == "__main__":
    log_file_path = sys.argv[1]
    report = investigate_logs(log_file_path)
    send_to_slack(report)
    print("Analysis completed. Report sent to Slack.")