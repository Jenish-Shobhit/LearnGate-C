import { test, expect } from "vitest";
import { render } from "@testing-library/react";
import Home from "../app/page";

test("renders root page without crashing", () => {
  render(<Home />);
  expect(document.body).toBeTruthy();
});
