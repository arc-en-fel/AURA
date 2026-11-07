import fs from 'fs';
import path from 'path';

// Pre-load frontend/.env into process.env for Node test runner
const envPath = path.resolve(process.cwd(), '.env');
if (fs.existsSync(envPath)) {
  const content = fs.readFileSync(envPath, 'utf8');
  content.split('\n').forEach((line) => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#')) {
      const idx = trimmed.indexOf('=');
      if (idx !== -1) {
        const k = trimmed.substring(0, idx).trim();
        const v = trimmed.substring(idx + 1).trim();
        process.env[k] = v;
      }
    }
  });
}

const { runCSVResolverTests } = await import('./csvResolver.test');
const { runStatusMappingTests } = await import('./statusMapping.test');
const { runCRMColorTests } = await import('./crmColors.test');
const { runProductionCleanupTests } = await import('./productionCleanup.test');
const { runStatusDistributionSyncTests } = await import('./statusDistributionSync.test');
const { runFrontendTests } = await import('./api.test');

const resolverRes = runCSVResolverTests();
const statusRes = await runStatusMappingTests();
const colorRes = runCRMColorTests();
const cleanupRes = await runProductionCleanupTests();
const syncRes = await runStatusDistributionSyncTests();

runFrontendTests().then(({ failed }) => {
  const totalFailed = failed + resolverRes.failed + statusRes.failed + colorRes.failed + cleanupRes.failed + syncRes.failed;
  if (totalFailed > 0) {
    process.exit(1);
  }
});
