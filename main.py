import json
import os
import ollama
import re


class TeamMember:
    def __init__(self, data):
        self.role = data['Role']
        self.responsibilities = data['Responsibilities']
        self.produces = {item['Artifact']: item['SendTo'] for item in data['Produces']}


class TeamOrchestrator:
    def __init__(self, team_file, need_file):
        with open(team_file, 'r') as f:
            team_data = json.load(f)
        self.team = {member['Role']: TeamMember(member) for member in team_data}
        self.artifacts = {}
        self.product_owner = self.team["Product Owner"]
        with open(need_file, 'r') as file:
            self.artifacts['customer_need.md'] = file.read().strip()

    def save_artifact(self, name, content):
        os.makedirs("out", exist_ok=True)
        if name in self.artifacts:
            version = 1
            while os.path.exists(f"out/{name}.{version}"):
                version += 1
            os.rename(f"out/{name}", f"out/{name}.{version}")

        content = re.sub(r'```\w*\n?', '', content)
        content = content.strip()

        with open(f"out/{name}", 'w') as f:
            f.write(content)
        self.artifacts[name] = content

    def generate_system_prompt(self, team_member):
        artifact_options = "\n".join(
            [f"- {artifact} (send to {recipient})" for artifact, recipient in team_member.produces.items()])
        prompt = f"""You are the {team_member.role} in the Digital Shore Team.

Your responsibilities are: {team_member.responsibilities}

You can produce the following artifacts (choose one):
{artifact_options}

Current artifacts:
{self.get_artifacts_summary()}

Your task is to generate exactly one artifact based on the current state of the project.
Use the following format for your response:

Artifact: <name of artifact file>
To: <role of team member to send artifact to>

Contents:
<contents of the file>

Remember:
1. You can only create artifacts that are in your list of producible artifacts.
2. The artifact name and recipient must match exactly with the options provided.
3. Do not use triple backticks (```) in your response.
"""
        return prompt

    def get_artifacts_summary(self):
        return "\n".join(
            [f"<artifact>{name}\n{content}</artifact>" for name, content in self.artifacts.items()])

    def parse_response(self, response):
        artifact_match = re.search(r'Artifact:\s*(.*?)\n', response)
        to_match = re.search(r'To:\s*(.*?)\n', response)
        content_match = re.search(r'Contents:\n(.*)', response, re.DOTALL)

        if not all([artifact_match, to_match, content_match]):
            raise ValueError("Response does not match expected format")

        return {
            'artifact': artifact_match.group(1).strip(),
            'to': to_match.group(1).strip(),
            'content': content_match.group(1).strip()
        }

    def run(self):
        print("Deploying the Digital Shore Team!")
        current_member = self.product_owner
        while True:
            print(f"\nCurrent team member: {current_member.role}")
            print("Generating artifact...", end="", flush=True)

            prompt = self.generate_system_prompt(current_member)

            try:
                response = ollama.chat(model="mixtral:8x22b-instruct", messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please perform your role and generate an artifact."}
                ])
                output = response['message']['content']
                parsed_output = self.parse_response(output)
            except Exception as e:
                print(f"\nFailed with: {e}")
                print("Full response:")
                print(output)
                print("\nRetrying...")
                continue

            print("\rArtifact generated.   ")

            artifact_name = parsed_output['artifact']
            to_member = parsed_output['to']
            content = parsed_output['content']

            if artifact_name not in current_member.produces:
                print(f"\nError: {artifact_name} is not a valid artifact for {current_member.role}. Retrying.")
                continue

            if current_member.produces[artifact_name] != to_member:
                print(
                    f"\nError: {artifact_name} should be sent to {current_member.produces[artifact_name]}, not {to_member}. Retrying.")
                continue

            self.save_artifact(artifact_name, content)

            print(f"Created: {artifact_name}")
            print(f"Sent to: {to_member}")

            if artifact_name == "product_release_announcement.md" and to_member == "Customers":
                print("\nProduct release announcement created. Development process completed.")
                break

            current_member = self.team[to_member]


if __name__ == "__main__":
    orchestrator = TeamOrchestrator("team.json", "customer_need.md")
    orchestrator.run()
