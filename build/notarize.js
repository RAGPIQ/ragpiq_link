const { notarize, stapleApp } = require('@electron/notarize');

exports.default = async function notarizing(context) {
  const { electronPlatformName, appOutDir } = context;
  if (electronPlatformName !== 'darwin') return;

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${appOutDir}/${appName}.app`;

  console.log(`🚀 Notarizing ${appPath}...`);

  await notarize({
    appBundleId: process.env.NOTARIZE_APP_BUNDLE_ID,
    appPath,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID
  });

  console.log(`✅ Notarization submitted. Waiting before stapling...`);

  // Retry staple with 30s delay and max attempts
  for (let i = 0; i < 5; i++) {
    try {
      await stapleApp(appPath);
      console.log(`📌 Stapled successfully on attempt ${i + 1}`);
      return;
    } catch (err) {
      console.warn(`🔁 Staple attempt ${i + 1} failed: ${err.message}`);
      if (i === 4) throw err;
      await new Promise(res => setTimeout(res, 30000));
    }
  }
};