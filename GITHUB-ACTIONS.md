# GitHub Actions

## Continuous integration

Commit the project files, including `.github/workflows/`, to the GitHub repository. Enable Actions in repository settings and use `main` as the default branch. Protect `main` with a ruleset that requires these checks after their first run:

- Pytest
- Docker build (sqlite)
- Docker build (azure-sql)
- Python dependency audit

CI runs on pull requests and pushes to `main`. It needs no repository secrets. Pytest uses a fresh GitHub-hosted runner, temporary SQLite files, and synthetic test accounts. Container checks build both images and run diagnostic commands without starting the app or contacting a database. The pip cache is keyed on the relevant requirements files. Keep real SQLite files, backups, `.env`, and credentials out of the repository and CI artifacts.

## Optional Azure deployment

The manual workflow is disabled by default. Leave the repository Actions variable `ENABLE_AZURE_DEPLOYMENT` unset or set it to `false` until staging and provisioning are complete. The job accepts only a dispatch on `main` and verifies that CI succeeded for the exact commit on a `main` push. PR checks alone do not satisfy the gate.

1. Create the GitHub environment `azure-production`. Restrict deployments to the protected `main` branch and require approval if your GitHub plan supports it. Keep workflow changes subject to branch review.
2. Create an Azure Entra federated identity credential for the GitHub environment. Use issuer `https://token.actions.githubusercontent.com` and audience `api://AzureADTokenExchange` for Azure public cloud. Match the repository's actual subject. The legacy default is `repo:OWNER/REPO:environment:azure-production`. Repositories with immutable subject claims use `repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:azure-production`. See [GitHub OIDC in Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure) and the [OIDC subject reference](https://docs.github.com/en/actions/reference/security/oidc).
3. Grant the deploying principal permission to read and update the existing Container App at the app scope. Grant ACR management-plane read for registry discovery and data-plane push for `household-chores`. Use `AcrPush` on an RBAC-only registry or repository-scoped `Container Registry Repository Writer` where ABAC is enabled. Configure the app's own managed identity and registry pull access separately, using `AcrPull` or repository-scoped `Container Registry Repository Reader` as appropriate. Keep registry admin credentials disabled. See [Microsoft's ACR role reference](https://learn.microsoft.com/azure/container-registry/container-registry-roles).
4. Add these six Actions variables to the GitHub environment or repository:

| Variable | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Federated principal client ID |
| `AZURE_TENANT_ID` | Azure tenant |
| `AZURE_SUBSCRIPTION_ID` | Subscription containing the configured resources |
| `AZURE_ACR_NAME` | Existing Azure Container Registry name |
| `AZURE_RESOURCE_GROUP` | Resource group containing the app |
| `AZURE_CONTAINER_APP_NAME` | Existing Container App name |

The deploy workflow needs no GitHub Actions client secret, registry password, or database credential. Keep the production `DATABASE_URL` and owner setup key in Azure Container Apps secrets and configure them on the existing app before enabling deploys. Run the Azure SQL schema migration separately with the appropriate principal. The workflow publishes an image and changes only the image on the existing app. Follow [AZURE-SQL.md](AZURE-SQL.md) to validate SQL connectivity, proxy trust, and probes first. Use single revision mode if all production traffic should follow the new revision automatically. In multiple revision mode, validate traffic routing separately.

After staging succeeds, set `ENABLE_AZURE_DEPLOYMENT=true` as a **repository-level** Actions variable. In Actions, choose **Deploy to Azure Container Apps**, select `main`, and dispatch. The workflow pushes a uniquely tagged image, deploys by digest, and waits for Azure to report the updated revision as ready. Then verify the public `/healthz` endpoint and sign-in. Disabling the repository variable prevents future runs and leaves the current deployment running.

## Troubleshooting

| Symptom | Where to look |
| --- | --- |
| Pytest fails | Open the test job and rerun the first failing test locally with `python -m pytest path/to/test.py -k test_name -vv`. The suite uses temporary data. |
| Dependency audit fails | Review the advisory ID and affected package. Update the runtime requirements and rerun CI. For advisory service errors, rerun when service is restored. |
| Docker build fails | Check the matrix variant. Rebuild locally with `docker build -f Dockerfile .` or `docker build -f Dockerfile.azure .`. ODBC or package repository failures appear in the Azure build. |
| Deployment skipped or fails preflight | Confirm the repository variable, branch, successful CI push run for the exact commit, and the six environment variables. |
| Azure login fails | Verify the client ID, tenant, audience, and exact OIDC subject, including environment name and any immutable IDs. `AADSTS700213` usually indicates a federated subject mismatch. |
| Push fails | Check registry discovery permissions, data-plane role, registry reachability from the runner, and ABAC scope. |
| Revision is unhealthy | Inspect the new revision's system and container logs. Check image pull identity, SQL configuration and Alembic head, port 8000, trusted proxy configuration, and health probe. Compare the last known-good digest before switching back. This workflow does not automatically roll back or run database migrations. |
