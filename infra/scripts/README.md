# Operational scripts

These scripts drive the production deployment. None of them stores the address,
the administrator account or the storage endpoints of that deployment: those are
read from environment variables, or passed explicitly as parameters. A script
that cannot resolve a required setting stops with the variable name rather than
guessing.

## Environment variables

Values belong in your shell profile or a secret manager, never in this
repository.

| Variable | Used by | Holds |
|---|---|---|
| `SPLITBIND_VM_HOST` | deploy, update, enable-fingerprint, sync-ssh-ip | Address of the production VM |
| `SPLITBIND_VM_ADMIN_USER` | all five scripts | SSH administrator account on that VM |
| `SPLITBIND_ACME_EMAIL` | deploy | Registration address for the certificate authority |
| `SPLITBIND_DATABASE_HOST` | deploy | Managed PostgreSQL hostname |
| `SPLITBIND_DATABASE_URL` | deploy | Full connection string, including credentials |
| `SPLITBIND_R2_ENDPOINT` | deploy | S3-compatible storage endpoint |
| `SPLITBIND_R2_BUCKET` | deploy | Bucket name |
| `SPLITBIND_R2_ACCESS_KEY` | deploy | Storage access key |
| `SPLITBIND_R2_SECRET_KEY` | deploy | Storage secret key |
| `SPLITBIND_ADMIN_PASSWORD` | deploy | Bootstrap administrator password |

## Setting them for a session

```powershell
$env:SPLITBIND_VM_HOST = "<address>"
$env:SPLITBIND_VM_ADMIN_USER = "<account>"
```

Any parameter still overrides its variable, so `-VmHost <address>` works for a
one-off run against a different target.

## Scripts

| Script | Purpose |
|---|---|
| `deploy_integrity_release.ps1` | First-time provisioning of the release onto a fresh VM |
| `update_production_release.ps1` | Routine rollout: sync compose, migrate, restart, verify |
| `enable_fingerprint_capability.ps1` | Turn transformed attribution on or off, generating the key on the VM |
| `sync_azure_ssh_ip.ps1` | Pin the SSH allow rule to the current workstation address |
| `audit_integrity_release_azure.ps1` | Read-only preflight audit of the Azure resources |
| `validate_compose_contract.py` | Contract checks over the Compose topology |
