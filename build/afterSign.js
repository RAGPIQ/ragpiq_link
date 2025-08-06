// build/afterSign.js
const path = require('path');
const { sign } = require('@electron/osx-sign');
const { notarize } = require('@electron/notarize');
const fs = require('fs');

exports.default = async function afterSign(context) {
  const { electronPlatformName, appOutDir } = context;

  if (electronPlatformName !== 'darwin') {
    console.log('🛑 Skipping notarization: not macOS');
    return;
  }

  const appPath = path.join(appOutDir, `${context.packager.appInfo.productFilename}.app`);

  console.log(`🔏 Signing macOS app at ${appPath}...`);

  await sign({
    app: appPath,
    identity: process.env.CSC_NAME,
    'hardened-runtime': true,
    entitlements: 'build/entitlements.mac.plist',
    'entitlements-inherit': 'build/entitlements.mac.plist',
    'signature-flags': 'library',
    'gatekeeper-assess': false,
    'strict-verification': false,
    filter: (filePath) => {
      const skipExts = ['.txt', '.py', '.pyc', '.sh', '.md', '.tcl', '.rst', '.jpeg', '.jpg', '.png', '.gif', '.tiff'];
      return !skipExts.some(ext => filePath.endsWith(ext));
    }
  });

  console.log(`✅ App signed. Proceeding to notarize...`);

  await notarize({
    appBundleId: process.env.NOTARIZE_APP_BUNDLE_ID,
    appPath,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
    tool: 'notarytool',
    waitForProcessing: true,
  });

  console.log(`📌 Successfully notarized and stapled: ${appPath}`);
};