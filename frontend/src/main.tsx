// The page's entry: the theme, then the chat page with the notebook panel inside it.
import { createRoot } from "react-dom/client";
import { ChatApp } from "@/chat/ChatApp";
import "./styles/theme.css";
import "./panel/styles.css";

const root = document.getElementById("root");
if (root) createRoot(root).render(<ChatApp />);
