// build/afterSign.js
const path = require('path');
const { sign } = require('@electron/osx-sign');
const { notarize } = require('@electron/notarize');
const { execSync } = require('child_process');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

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
      const skipExts = [
        '.txt', '.py', '.pyc', '.sh', '.md', '.tcl', '.rst', '.jpeg',
        '.jpg', '.png', '.gif', '.tiff', '.a', '.pak', '.icns'
      ];
      const skipNames = [
        'tkConfig.sh', 'tclConfig.sh', 'tclooConfig.sh', 'libtclstub8.6.a',
        'Tcl', 'Tk'
      ];
      return (
        !skipExts.some(ext => filePath.endsWith(ext)) &&
        !skipNames.some(name => filePath.endsWith(name))
      );
    }
  });

  console.log('🔁 Running final deep codesign...');
  execSync(`codesign --deep --force --options runtime --sign "${process.env.CSC_NAME}" "${appPath}"`, {
    stdio: 'inherit'
  });

  console.log('⏳ Waiting for file sync to settle...');
  await sleep(3000);

  if (
    !process.env.NOTARIZE_APP_BUNDLE_ID ||
    !process.env.APPLE_ID ||
    !process.env.APPLE_APP_SPECIFIC_PASSWORD ||
    !process.env.APPLE_TEAM_ID
  ) {
    console.log('⚠️ Skipping notarization: required Apple credentials not set.');
    return;
  }

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

  console.log(`✅ App notarized. Waiting before stapling...`);
  await sleep(15000);
  
  try {
    execSync(`xcrun stapler staple -v "${appPath}"`, { stdio: 'inherit' });
    console.log(`📌 Stapling complete.`);
  } catch (err) {
    console.warn('⚠️ Stapling failed. Waiting and retrying...');
    await sleep(15000);
    try {
      execSync(`xcrun stapler staple -v "${appPath}"`, { stdio: 'inherit' });
      console.log(`✅ Stapling succeeded after retry.`);
    } catch (retryErr) {
      console.error('❌ Stapling failed again. Notarization may still be valid.');
      throw retryErr;
    }
  }
};