// build/afterSign.js
const path = require('path');
const { notarize } = require('@electron/notarize');
const { execSync } = require('child_process');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function stapleWithRetry(appPath, attempts = 5, delay = 30000) {
  for (let i = 1; i <= attempts; i++) {
    try {
      execSync(`xcrun stapler staple -v "${appPath}"`, { stdio: 'inherit' });
      console.log(`📌 Stapling complete (attempt ${i}).`);
      return;
    } catch (err) {
      if (i === attempts) {
        console.error('❌ Stapling failed after maximum retries.');
        throw err;
      }
      console.warn(`⚠️ Stapling failed on attempt ${i}. Waiting before retry...`);
      await sleep(delay);
    }
  }
}

exports.default = async function afterSign(context) {
  const { electronPlatformName, appOutDir } = context;

  if (electronPlatformName !== 'darwin') {
    console.log('🛑 Skipping notarization: not macOS');
    return;
  }

  const appPath = path.join(appOutDir, `${context.packager.appInfo.productFilename}.app`);
  console.log(`✅ Verifying signature before notarization...`);

  try {
    execSync(`codesign --verify --deep --strict --verbose=2 "${appPath}"`, { stdio: 'inherit' });
    console.log(`✅ App is correctly signed.`);
  } catch (err) {
    console.error('❌ Signature verification failed. Aborting notarization.');
    throw err;
  }

  if (
    !process.env.NOTARIZE_APP_BUNDLE_ID ||
    !process.env.APPLE_ID ||
    !process.env.APPLE_APP_SPECIFIC_PASSWORD ||
    !process.env.APPLE_TEAM_ID
  ) {
    console.log('⚠️ Skipping notarization: required Apple credentials not set.');
    return;
  }

  console.log(`🚀 Notarizing app...`);

  await notarize({
    appBundleId: process.env.NOTARIZE_APP_BUNDLE_ID,
    appPath,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
    tool: 'notarytool',
    waitForProcessing: true,
  });

  console.log(`✅ App notarized. Stapling...`);
  await stapleWithRetry(appPath);
};