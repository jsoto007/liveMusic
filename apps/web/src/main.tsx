import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./context/AuthContext";
import "./styles/classical.css";
import "./styles/app.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("No #root element — index.html is not the document that loaded.");
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
