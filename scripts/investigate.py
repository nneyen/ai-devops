import os 
import sys 
import json 
import requests 
from openai import OpenAI
from slack_sdk import WebClient

# Metadata for GitHub Environment
workflow_name = os.getenv("GITHUB_WORKFLOW_NAME", "Unknown Workflow")
job_name = os.getenv("TARGET_JOB_NAME", "Unknown Job")
repository = os.getenv("GITHUB_REPOSITORY", "Unknown Repository")
run_id = os.getenv("GITHUB_RUN_ID", "Unknown Run ID")
slack_webhook_url = os.getenv("SLACK_WEBHOOK")
actor = os.getenv("GITHUB_ACTOR", "Unknown Actor")


# Function to Investigate Logs
def investigate_logs(log_file_path):
    
    # READ AND TRUNCATE LOGS
    if not os.path.exists(log_file_path):
        return "File does not exist"
    with open(log_file_path, 'r') as file:
        logs = file.readlines()

        if len(logs) > 2000:
            head = "".join(logs[:200])
            tail = "".join(logs[-1800:])
            tail_logs = f"{head}\n\n... [TRUNCATED {len(logs)-2000} LINES ] ...\n\n{tail}"
        else:
            tail_logs = "".join(logs)

    # CONFIGURE AI CLIENT
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # CONFIGURE AI SYSTEM PROMPT
    system_prompt = """
    You are a senior DevOps engineer performing automated CI/CD failure triage for GitHub Actions workflows.
    You will be given GitHub Actions job logs (possibly truncated) and workflow metadata.
    Your objective is to minimize investigation time for the on-call engineer.
    Output ONLY A VALID JSON OBJECT.
    
    Strict rules:
    - Identify the earliest *actionable* failure in execution order.
    - Ignore secondary, cascading, or cleanup errors.
    - Do NOT speculate beyond what is present in the logs.
    - If the logs do not contain a concrete root error, state this explicitly.
    - Prefer accuracy and clarity over completeness.
    """

    # CONFIGURE AI USER PROMPT
    user_prompt = f"""
    Analyse these logs for Repo: {repository}, Workflow: {workflow_name}, Job: {job_name}, Run URL: https://github.com/{repository}/actions/runs/{run_id}

    --- BEGINNING OF LOGS ---
    {tail_logs}
    --- END OF LOGS ---
    
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

    OUTPUT FORMAT (JSON ONLY):
    {{
        "category": "infra | dependency | auth | config | test | timeout",
        "confidence": "High | Medium | Low",
        "earliest_failure": "Exact error line from logs",
        "root_cause": "1-2 sentence explanation",
        "next_steps": ["step 1", "step 2", "step 3", "step 4"]
    }}
    
    Do NOT include raw logs.
    Do NOT add commentary outside this format.
    """

    # ASK AI TO INVESTIGATE
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={
            "type": "json_object",
            "json_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "confidence": {"type": "string"},
                    "earliest_failure": {"type": "string"},
                    "root_cause": {"type": "string"},
                    "next_steps": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["category", "confidence", "earliest_failure", "root_cause", "next_steps"]
            }
        },
        temperature=0.1,
        max_tokens=800
    )
    return json.loads(response.choices[0].message.content)  

# Function to Send Report to Slack
def send_to_slack(slack_webhook_url, message, run_url):
    # Send Report to Slack
    if not slack_webhook_url:
        raise ValueError("SLACK_WEBHOOK environment variable is not set")
    
    # Format the message for Slack
    icons = {
        "infra": "☁️", "dependency": "📦", "auth": "🔐", 
        "config": "⚙️", "test": "🧪", "timeout": "⏳"
    }
    icon = icons.get(message.get("category", "").lower(), "❓")
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔴*Pipeline Failure Analysis* 🔴",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Category:*\n{icon}`{message.get('category')}`"},
                    {"type": "mrkdwn", "text": f"*Confidence:*\n`{icon}`{message.get('confidence')}`"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Earliest Failure:*\n```{message.get('earliest_failure')}```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause Assessment:*\n```{message.get('root_cause')}```"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Remediation Steps:*\n" + "\n".join([f"- {step}" for step in message.get("remediation", [])])
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📍 *Repo:* {repository}  |  🆔 *Run ID:* {os.getenv('GITHUB_RUN_ID')} | 👤 *Actor:* {os.getenv('GITHUB_ACTOR')}"
                    }
                ]
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
    }

    response = requests.post(slack_webhook_url, json=payload)
    if response.status_code != 200:
        raise Exception("Failed to send Slack notification")
    print("Slack notification sent successfully")

if __name__ == "__main__":
    log_file_path = sys.argv[1]
    report = investigate_logs(log_file_path)

    webhook_url = os.getenv("SLACK_WEBHOOK")
    repo = os.getenv("GITHUB_REPOSITORY", "Unknown/Repo")
    run_id = os.getenv("GITHUB_RUN_ID", "0")
    
    # Construct the Run URL for the Slack button
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}"

    send_to_slack(webhook_url, report, run_url)
    print("Analysis completed. Report sent to Slack.")