// build/afterSign.js
const path = require('path');
const { sign } = require('@electron/osx-sign');
const { notarize } = require('@electron/notarize');

exports.default = async function afterSign(context) {
  const appPath = path.join(
    context.appOutDir,
    `${context.packager.appInfo.productFilename}.app`
  );

  console.log(`🔏 Signing macOS app at ${appPath}...`);

  await sign({
    app: appPath,
    identity: process.env.CSC_NAME, // Set this in GitHub Secrets
    'hardened-runtime': true,
    entitlements: 'build/entitlements.mac.plist',
    'entitlements-inherit': 'build/entitlements.mac.plist',
    'signature-flags': 'library',
    'gatekeeper-assess': false,
    'strict-verification': false,
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