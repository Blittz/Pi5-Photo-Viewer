#!/bin/bash

# Go to the directory of this script
cd "$(dirname "$0")"

# Prompt for commit message
read -p "Enter a commit message: " msg

# Show what will be committed
echo "=============================="
echo "Changes to be committed:"
git status
echo "=============================="

# Confirm before committing
read -p "Proceed with commit? (y/n): " confirm
if [[ $confirm != "y" ]]; then
    echo "Aborting."
    exit 1
fi

# Stage all changes
git add -A

# Commit
git commit -m "$msg"

# Push to origin
git push

echo "✅ Changes pushed to GitHub."
