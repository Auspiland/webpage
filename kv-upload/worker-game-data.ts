/**
 * Cloudflare Worker: 게임 데이터 조회 API
 *
 * 엔드포인트:
 * - GET /game1/{key} - 특정 키의 데이터 조회 (예: /game1/5)
 * - GET /game1/list - 모든 키 목록 조회
 * - GET /game1/all - 모든 데이터를 원본 형식으로 조회
 */

interface Env {
  KV: KVNamespace;
}

const KEY_PREFIX = 'game1_';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const pathParts = url.pathname.split('/').filter(p => p);

    // CORS 헤더
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Content-Type': 'application/json',
    };

    // OPTIONS 요청 처리 (CORS preflight)
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // GET /game1/{key} - 특정 키의 데이터 조회
      if (pathParts[0] === 'game1' && pathParts[1] && pathParts[1] !== 'list' && pathParts[1] !== 'all') {
        const key = pathParts[1];
        const kvKey = `${KEY_PREFIX}${key}`;

        const value = await env.KV.get(kvKey, { type: 'json' });

        if (value === null) {
          return new Response(JSON.stringify({
            success: false,
            error: `Key '${key}' not found`,
            message: `게임 데이터 키 '${key}'를 찾을 수 없습니다.`
          }), {
            status: 404,
            headers: corsHeaders,
          });
        }

        return new Response(JSON.stringify({
          success: true,
          key: key,
          data: value,
          length: Array.isArray(value) ? value.length : 0
        }), {
          headers: corsHeaders,
        });
      }

      // GET /game1/list - 모든 키 목록 조회
      if (pathParts[0] === 'game1' && pathParts[1] === 'list') {
        const listResult = await env.KV.list({ prefix: KEY_PREFIX });

        const keys = listResult.keys.map(k => {
          // 'game1_5' -> '5'
          return k.name.replace(KEY_PREFIX, '');
        });

        return new Response(JSON.stringify({
          success: true,
          keys: keys.map(Number).sort((a, b) => a - b), // 숫자로 변환하여 정렬
          count: keys.length
        }), {
          headers: corsHeaders,
        });
      }

      // GET /game1/all - 모든 데이터를 원본 형식으로 조회
      if (pathParts[0] === 'game1' && pathParts[1] === 'all') {
        const listResult = await env.KV.list({ prefix: KEY_PREFIX });

        // 모든 키를 숫자로 추출하고 정렬
        const keys = listResult.keys
          .map(k => Number(k.name.replace(KEY_PREFIX, '')))
          .sort((a, b) => a - b);

        // 모든 데이터를 병렬로 가져오기
        const dataPromises = keys.map(key =>
          env.KV.get(`${KEY_PREFIX}${key}`, { type: 'json' })
        );
        const allData = await Promise.all(dataPromises);

        // 원본 형식으로 재구성: [[keys...], [data1...], [data2...], ...]
        const result = [keys, ...allData];

        return new Response(JSON.stringify(result), {
          headers: corsHeaders,
        });
      }

      // 루트 경로 - API 문서
      return new Response(JSON.stringify({
        name: 'Game Data API',
        version: '1.0.0',
        endpoints: {
          'GET /game1/{key}': {
            description: '특정 키의 게임 데이터 조회',
            example: '/game1/5',
            response: {
              success: true,
              key: '5',
              data: '[배열 데이터]',
              length: '배열 길이'
            }
          },
          'GET /game1/list': {
            description: '모든 키 목록 조회',
            example: '/game1/list',
            response: {
              success: true,
              keys: '[1, 2, 3, ...]',
              count: '키 개수'
            }
          },
          'GET /game1/all': {
            description: '모든 데이터를 원본 JSON 형식으로 조회',
            example: '/game1/all',
            response: '[[keys...], [data1...], [data2...], ...]'
          }
        },
        usage: {
          example1: 'fetch("https://your-worker.workers.dev/game1/10").then(r => r.json())',
          example2: 'fetch("https://your-worker.workers.dev/game1/list").then(r => r.json())',
          example3: 'fetch("https://your-worker.workers.dev/game1/all").then(r => r.json())'
        }
      }, null, 2), {
        headers: corsHeaders,
      });

    } catch (error) {
      return new Response(JSON.stringify({
        success: false,
        error: error.message || 'Internal Server Error'
      }), {
        status: 500,
        headers: corsHeaders,
      });
    }
  },
};
