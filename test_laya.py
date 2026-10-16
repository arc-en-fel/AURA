from laya import load

print("Loading Laya model...", flush=True)
agent = load("convaiinnovations/laya")
print("Model loaded successfully!", flush=True)

state = "The customer was charged twice and requests a refund."
questions = {
    "department": {
        "type": "choice",
        "instructions": "Which department should handle this?",
        "criteria": {
            "billing": "Payments, invoices and refunds",
            "technical": "Software bugs and technical issues",
            "other": "Other requests"
        }
    }
}

result = agent.predict(state, questions)
print("Inference result:", result)
