const { getDefaultConfig } = require("expo/metro-config");

module.exports = (async () => {
  const config = await getDefaultConfig(__dirname);
  config.server = {
    ...config.server,
    allowedHosts: ["all"],
  };
  return config;
})();