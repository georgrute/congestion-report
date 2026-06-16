import os
import requests
from datetime import datetime, timedelta

# API Configuration
API_URL = "https://congestion-tracker-api.claw.gridraven.com/api/v1/congestion/lines-timeseries"
SLACK_API_URL = "https://slack.com/api/chat.postMessage"
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

def get_congestion_data():
    # Calculate past 72-hour window in ISO-8601 UTC format
    now = datetime.utcnow()
    three_days_ago = now - timedelta(hours=72)
    
    params = {
        "from": three_days_ago.strftime("%Y-%m-%dT%H:00:00Z"),
        "to": now.strftime("%Y-%m-%dT%H:00:00Z")
    }
    
    response = requests.get(API_URL, params=params)
    response.raise_for_status()
    return response.json()

def process_top_lines(data):
    lines_summary = []
    
    for line in data.get("lines", []):
        line_name = line["name"]
        total_da_cost = 0.0
        total_rt_cost = 0.0
        
        for entry in line.get("ratings", []):
            # Sum Day-Ahead costs
            if entry.get("da") and entry["da"].get("old_price") is not None:
                total_da_cost += entry["da"]["old_price"]
            # Sum Real-Time costs
            if entry.get("rt") and entry["rt"].get("old_price") is not None:
                total_rt_cost += entry["rt"]["old_price"]
                
        total_combined = total_da_cost + total_rt_cost
        
        lines_summary.append({
            "name": line_name,
            "da_cost": total_da_cost,
            "rt_cost": total_rt_cost,
            "total_cost": total_combined
        })
        
    top_5_da = sorted(lines_summary, key=lambda x: x["da_cost"], reverse=True)[:5]
    top_5_rt = sorted(lines_summary, key=lambda x: x["rt_cost"], reverse=True)[:5]
    return top_5_da, top_5_rt

def build_slack_blocks(top_5_da, top_5_rt):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 Top Congested Lines (Past 72 Hours)"}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Top 5 by Day-Ahead Cost*"}
        },
    ]

    for i, line in enumerate(top_5_da, 1):
        line_text = (
            f"*{i}. {line['name']}*\n"
            f"• *Day-Ahead Cost:* ${line['da_cost']:,.2f}"
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line_text}
        })

    blocks.extend([
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Top 5 by Real-Time Cost*"}
        },
    ])

    for i, line in enumerate(top_5_rt, 1):
        line_text = (
            f"*{i}. {line['name']}*\n"
            f"• *Real-Time Cost:* ${line['rt_cost']:,.2f}"
        )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line_text}
        })

    return blocks

def send_slack_notification(top_5_da, top_5_rt):
    blocks = build_slack_blocks(top_5_da, top_5_rt)

    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Slack credentials missing. Summary output:")
        print("Top 5 by Day-Ahead Cost:", top_5_da)
        print("Top 5 by Real-Time Cost:", top_5_rt)
        return

    response = requests.post(
        SLACK_API_URL,
        headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "channel": SLACK_CHANNEL_ID,
            "blocks": blocks,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Slack API error: {payload.get('error', 'unknown error')}")

if __name__ == "__main__":
    try:
        raw_data = get_congestion_data()
        top_5_da, top_5_rt = process_top_lines(raw_data)
        send_slack_notification(top_5_da, top_5_rt)
        print("Report successfully sent!")
    except Exception as e:
        print(f"Error executing report: {e}")