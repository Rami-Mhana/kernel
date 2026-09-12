import subprocess # use another program

done = {}

print(f"an empty dictionary {done}")

git_status_data = subprocess.run(["git", "status"], capture_output=True, text=True)
print(f"The status of this local repo: {git_status_data}")

