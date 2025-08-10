const fs = require('fs');
const path = require('path');

exports.default = async function afterPack(ctx) {
  const contents = ctx.appOutDir; // .../Ragpiq Link.app/Contents
  const py = path.join(contents, 'Resources', 'python', 'mac', 'Library', 'Frameworks', '3.13', 'bin', 'python3');
  try {
    if (fs.existsSync(py)) {
      await fs.promises.chmod(py, 0o755);
      console.log('[afterPack] chmod +x python3');
    }
  } catch (e) {
    console.warn('[afterPack] chmod python3 failed', e);
  }
};