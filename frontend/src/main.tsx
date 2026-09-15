import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./app/router";
import { AuthProvider } from "./auth/auth-provider";
import "./styles/tokens.css";
import "./styles/index.css";
import "./styles/light-migration.css";
import "./styles/anomaly-report.css";
import "./styles/showcase-redesign.css";
import "./styles/showcase-polish.css";
import "./styles/fleet-command-map-v2.css";
import "./styles/fleet-command-map-v3.css";
import "./styles/countyflow-night.css";
import "./styles/admin-overview.css";
import "./styles/fleet-command-map-v4.css";

// The provider intentionally wraps the router so every route guard shares one in-memory session.
createRoot(document.getElementById("root")!).render(<StrictMode><AuthProvider><RouterProvider router={router}/></AuthProvider></StrictMode>);
