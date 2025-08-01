console.log("🔐 Running notarize.js hook...");

require('dotenv').config();
const { notarize } = require('@electron/notarize');

const { stapleApp } = require('@electron/notarize');

async function stapleWithRetry(appPath) {
  for (let i = 0; i < 5; i++) {
    try {
      await stapleApp(appPath);
      return;
    } catch (e) {
      console.log(`🔁 Staple attempt ${i + 1} failed. Retrying in 30s...`);
      await new Promise(res => setTimeout(res, 30000));
    }
  }
  throw new Error('❌ Failed to staple after multiple attempts');
}

exports.default = async function notarizing(context) {
  const { electronPlatformName, appOutDir } = context;
  if (electronPlatformName !== 'darwin') return;

  const appName = context.packager.appInfo.productFilename;

  return await notarize({
    appBundleId: process.env.NOTARIZE_APP_BUNDLE_ID,
    appPath: `${appOutDir}/${appName}.app`,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID
  });
};