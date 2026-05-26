import { load, validate, reset } from '../config';

jest.mock('fs', () => {
  const actual = jest.requireActual('fs');
  return {
    ...actual,
    existsSync: (path: string) => {
      if (path.endsWith('.yaml') || path.includes('master.yaml')) return false;
      return actual.existsSync(path);
    },
  };
});

const ORIGINAL_CWD = process.cwd;

describe('Master Config', () => {
  beforeEach(() => {
    reset();
    delete process.env.CLUSTER_TOKEN;
    delete process.env.MASTER_PORT;
    delete process.env.LOG_LEVEL;
    delete process.env.INSPECTION_ENABLED;
  });

  afterAll(() => {
    process.cwd = ORIGINAL_CWD;
  });

  it('loads with defaults when no config file exists', () => {
    const cfg = load();
    expect(cfg.server.ws_port).toBe(32080);
    expect(cfg.server.host).toBe('0.0.0.0');
  });

  it('applies CLUSTER_TOKEN environment variable', () => {
    process.env.CLUSTER_TOKEN = 'my-production-token';
    const cfg = load();
    expect(cfg.cluster_token).toBe('my-production-token');
  });

  it('applies MASTER_PORT environment variable', () => {
    process.env.MASTER_PORT = '32080';
    const cfg = load();
    expect(cfg.server.ws_port).toBe(32080);
    expect(cfg.server.api_port).toBe(32080);
  });

  it('applies LOG_LEVEL environment variable', () => {
    process.env.LOG_LEVEL = 'debug';
    const cfg = load();
    expect(cfg.logging.level).toBe('debug');
  });

  describe('validate', () => {
    it('warns about dev default token', () => {
      const cfg = load();
      const { warnings } = validate(cfg);
      expect(warnings.some(w => w.field === 'cluster_token')).toBe(true);
    });

    it('errors on invalid body limit format', () => {
      const cfg = load();
      cfg.server.api.body_limit = '5xx';
      const { errors } = validate(cfg);
      expect(errors.some(e => e.field === 'server.api.body_limit')).toBe(true);
    });

    it('errors on zero max_connections', () => {
      const cfg = load();
      cfg.server.ws.max_connections = 0;
      const { errors } = validate(cfg);
      expect(errors.some(e => e.field === 'server.ws.max_connections')).toBe(true);
    });
  });
});
