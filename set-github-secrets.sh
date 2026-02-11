#!/bin/bash
# Set GitHub Actions secrets for Arctic sync

set -e

echo "🔐 Setting GitHub Actions secrets..."
echo ""

# Load .env file
if [ -f ".env" ]; then
    source .env
else
    echo "❌ Error: .env file not found"
    exit 1
fi

# Set secrets using gh CLI
echo "Setting OUTLINE_API_URL..."
gh secret set OUTLINE_API_URL --body "$OUTLINE_API_URL"

echo "Setting OUTLINE_API_KEY..."
gh secret set OUTLINE_API_KEY --body "$OUTLINE_API_KEY"

echo "Setting OUTLINE_DAY_TOURS_DOC_ID..."
gh secret set OUTLINE_DAY_TOURS_DOC_ID --body "$OUTLINE_DAY_TOURS_DOC_ID"

echo "Setting OUTLINE_MD_TOURS_DOC_ID..."
gh secret set OUTLINE_MD_TOURS_DOC_ID --body "$OUTLINE_MD_TOURS_DOC_ID"

echo ""
echo "✅ All secrets set successfully!"
echo ""
echo "Verify at: https://github.com/frigiddesert/data-cleaning-projects/settings/secrets/actions"
