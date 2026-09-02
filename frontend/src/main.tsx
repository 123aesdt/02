import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { router } from "./app/router";
import { AuthProvider } from "./auth/auth-provider";
import "./styles/tokens.css";
import "./styles/index.css";
import "./styles/light-migration.css";
import "./styles/anomaly-report.css";

// The provider intentionally wraps the router so every route guard shares one in-memory session.
createRoot(document.getElementById("root")!).render(<StrictMode><AuthProvider><RouterProvider router={router}/></AuthProvider></StrictMode>);
