import { registerApplication, start } from "single-spa";
import {
  constructApplications,
  constructLayoutEngine,
  constructRoutes,
} from "single-spa-layout";

import microfrontendLayout from "./microfrontend-layout.html";
import "./styles/global.css";
import { mountTechStack } from "./tech-stack";

// 1. Parse the declarative layout into a routes tree.
const routes = constructRoutes(microfrontendLayout);

// 2. Build application objects; each is lazily loaded via the import-map.
const applications = constructApplications({
  routes,
  loadApp({ name }) {
    return System.import(name);
  },
});

// 3. The layout engine mounts each application into its declared container.
const layoutEngine = constructLayoutEngine({ routes, applications });

// 4. Register + activate + start single-spa.
applications.forEach(registerApplication);
layoutEngine.activate();
start({ urlRerouteOnly: true });

// 5. Mount the "Tech stack" showcase button + modal (shell-level chrome).
mountTechStack();



