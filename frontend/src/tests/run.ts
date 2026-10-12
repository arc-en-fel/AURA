import { runFrontendTests } from './api.test';

runFrontendTests().then(({ failed }) => {
  if (failed > 0) {
    process.exit(1);
  }
});
