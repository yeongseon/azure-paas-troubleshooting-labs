---
hide:
  - toc
validation:
  az_cli:
    last_tested: null
    result: not_tested
  bicep:
    last_tested: null
    result: not_tested
  terraform:
    last_tested: null
    result: not_tested
---

# Backup and Restore: Partial Restore and Database Mismatch

!!! info "Status: Planned"

## 1. Question

App Service backup includes app content (`/home`) and optionally connected databases. When a backup is restored, what is the exact behavior when the database connection string in the restored app differs from the database state at the time of the backup — and does the restore leave the app in a consistent or inconsistent state?

## 2. Why this matters

App Service backup/restore is used for disaster recovery and environment cloning. Engineers often assume that restoring a backup restores the complete application state. In practice, the backup captures a point-in-time snapshot of files and database separately, and restoring them to a new environment may create a mismatch: the app code from the backup points to the old database URI, or the database schema at restore time is newer than what the backup expects. This is a common source of confusion when cloning production to staging.

## 3. Customer symptom

"We restored from backup but the app shows database connection errors" or "The restored app is missing records that were written after the backup" or "Restoring to a new app service doesn't work — we get 500 errors immediately after restore."

## 4. Hypothesis

- H1: When a backup is restored to a new App Service without also restoring the database, the app uses the new App Service's current app settings (which may point to a different database). If the connection string is set as an app setting (not captured in the backup's app settings), the app may connect to the wrong database.
- H2: When the backup includes a database dump and the dump is restored to the target database, the target database is overwritten with the backup's data. Any changes made to the target database after the backup point are lost.
- H3: The App Service backup does not capture slot-specific app settings (deployment slot settings). After restoring to a slot, the slot retains its current sticky settings regardless of what was in the backup.

## 5. Environment

| Parameter | Value |
|-----------|-------|
| Service | Azure App Service |
| SKU / Plan | P1v3 (Standard or higher required for backup) |
| Region | Korea Central |
| Runtime | Python 3.11 |
| OS | Linux |
| Date tested | — |

## 6. Variables

**Experiment type**: Deployment / Data consistency

**Controlled:**

- App Service with a Python app backed by a PostgreSQL database (Azure Database for PostgreSQL Flexible Server)
- Scheduled backup configured to capture both app content and database
- A staging slot with a different database connection string (sticky setting)

**Observed:**

- App behavior after restore to a new app (no database restore)
- App behavior after restore with database overwrite
- Slot-sticky settings behavior after restore

**Scenarios:**

- S1: Full backup → restore to new app with database → verify consistency
- S2: Partial backup restore (files only, no database) → observe connection error behavior
- S3: Write new records after backup → restore → verify data loss scope
- S4: Restore to staging slot → verify sticky settings are preserved

## 7. Instrumentation

- App Service **Backups** blade for backup status and restore log
- Application database query endpoint to verify record counts before/after restore
- App settings comparison (before and after restore)

## 8. Procedure

_To be defined during execution._

### Sketch

1. Deploy Python app with PostgreSQL; insert 100 records; take a full backup.
2. Insert 50 more records after backup (total 150).
3. S1: Restore backup to a new App Service with a fresh database; verify app starts with 100 records.
4. S2: Restore backup to another new app but do NOT restore the database; observe connection error (app tries to connect to the original database, which may not be accessible from the new app).
5. S3: Use the original app (150 records); restore the same backup in-place (overwrite); verify database is rolled back to 100 records.
6. S4: Restore to staging slot; verify slot-sticky `DB_CONNECTION_STRING` still points to staging database (not overwritten by backup).

## 9. Expected signal

- S1: App starts correctly; 100 records visible; 50 records written after backup are absent.
- S2: App starts but database connection fails (wrong server URI in connection string or inaccessible database); application returns 500.
- S3: Database rolled back to 100 records; 50 new records lost.
- S4: Staging slot uses staging database (sticky setting preserved); no data from backup's app settings overwrites the slot setting.

## 10. Results

_Awaiting execution._

## 11. Interpretation

_Awaiting execution._

## 12. What this proves

_Awaiting execution._

## 13. What this does NOT prove

_Awaiting execution._

## 14. Support takeaway

_Awaiting execution._

## 15. Reproduction notes

- Backup requires Standard or higher plan. Free and Basic plans do not support backup.
- The backup zip contains app content plus an optional SQL/MySQL dump file. App settings are included in the backup but may be overridden by current slot settings on restore.
- For environment cloning, using ARM templates or Bicep for infrastructure + a separate data migration is more reliable than backup/restore.

## 16. Related guide / official docs

- [Back up and restore your app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/manage-backup)
- [Restore an app in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/web-sites-restore)
