# Agent Rules for BNU CMS Wrapper API

- **Stats Logging Requirement**: Every new feature, page, or API endpoint added to the BNU CMS wrapper API must have its data tracking, visit count, success/failure rate, or performance logged in the `/stats` live dashboard.
- **Data Persistence Requirement**: When adding a new student-specific feature (e.g. new portal page, new data fetch endpoint), ensure its raw JSON response is written to the local disk under `student_data/` with the filename pattern `<username>_<datatype>.json` so that it is persists on the Render disk, and make sure it is linked/downloadable on the `/stats` admin panel.
