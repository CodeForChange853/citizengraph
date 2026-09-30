import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import i18n from "../i18n";
import { reloadChat } from "../lib/chatStore";
import { reloadChecklists } from "../lib/checklistStore";
import { reloadSettings } from "../lib/settings";

beforeEach(async () => {
  localStorage.clear();
  reloadChecklists();
  reloadChat();
  reloadSettings();
  await i18n.changeLanguage("en");
});

afterEach(() => {
  cleanup();
});
