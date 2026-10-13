# Third-Party Notices

This project includes the following third-party packages and their licenses. The client build (bundled in `client/dist/`) is committed, so these runtime dependencies are included in every deployment.

## Frontend (JavaScript / Node.js) Production Dependencies

| Package | Version | License |
|---------|---------|---------|
| `animejs` | ^3.2.2 | MIT |
| `axios` | ^1.20.0 | MIT |
| `react` | ^19.2.8 | MIT |
| `react-dom` | ^19.2.8 | MIT |
| `zustand` | ^5.0.15 | MIT |
| `tailwindcss` | ^3.4.19 | MIT |
| `postcss` | ^8.5.28 | MIT |
| `autoprefixer` | ^10.5.5 | MIT |
| `@types/animejs` | ^3.1.13 | MIT |

**Note:** All npm production dependencies are bundled by Vite into `client/dist/`, which is committed to the repository. The bundled JavaScript includes transitive dependencies not listed here. For a complete list of all transitive dependencies and their licenses, run `npm ls --production` in the `client/` directory.

## Backend (Python) Production Dependencies

| Package | Version | License |
|---------|---------|---------|
| `fastapi` | >=0.141.1 | MIT |
| `uvicorn` | >=0.52.4 | BSD-3-Clause |
| `databricks-sdk` | >=0.138.0 | MIT |
| `pydantic` | >=2.13.5 | MIT |
| `pyyaml` | >=6.0.3 | MIT |
| `psycopg` | >=3.3.5 | LGPL-3.0-or-later |
| `psycopg_pool` | >=3.3.3 | LGPL-3.0-or-later |
| `openai` | >=3.27.0 | MIT |

**Note:** The backend also depends on `pytest>=8.0` and other test dependencies, which are not included in production deployments.

## License Compliance

All third-party licenses are compatible with the Databricks License (see LICENSE). For questions about license compliance, contact Databricks Legal.
