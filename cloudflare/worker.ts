import { Container } from "@cloudflare/containers";

export class RunO2Container extends Container {
  defaultPort = 8080;
  sleepAfter = "2m";
}

interface Env {
  RUNO2: DurableObjectNamespace<RunO2Container>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const container = env.RUNO2.getByName("runo2-app");
    return container.fetch(request);
  },
};
