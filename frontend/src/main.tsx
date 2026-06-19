import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import ParticipantPage from "./ParticipantPage";
import RegistrationPage from "./RegistrationPage";
import "./styles.css";

const Page = window.location.pathname === "/participant" ? ParticipantPage : window.location.pathname === "/register" ? RegistrationPage : App;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
