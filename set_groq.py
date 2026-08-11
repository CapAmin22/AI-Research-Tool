import json, os
path = os.path.expanduser('~/.agent-reach/config.json')
data = {}
if os.path.exists(path):
    with open(path, 'r') as f:
        data = json.load(f)
data['groq-key'] = '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'
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump(data, f, indent=4)
print('Groq configured!')
