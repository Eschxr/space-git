import type { NextConfig } from 'next';
const config: NextConfig = { output: process.env.SPACEGIT_STATIC === '1' ? 'export' : undefined, poweredByHeader: false, experimental: { cpus: 2 } };
export default config;
