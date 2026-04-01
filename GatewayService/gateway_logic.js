require('dotenv').config();
const WebSocket = require('ws');
const k8s = require('@kubernetes/client-node');
const url = require('url');
const http = require('http');
const https = require('https');

const kc = new k8s.KubeConfig();
kc.loadFromCluster();
console.log('Loaded Kubernetes config from cluster (using service account)');


const k8sApi = kc.makeApiClient(k8s.CoreV1Api);

const NAMESPACE = process.env.NAMESPACE;
const AUTH_API_URL = process.env.AUTH_API_URL || 'https://uatocrdemo.finigami.com/v1/user';
const PORT = '8080';

if (!NAMESPACE || !AUTH_API_URL || !PORT) {
  console.error('NAMESPACE, AUTH_API_URL, and PORT must be set');
  process.exit(1);
}

// Create HTTP server with WebSocket
const server = http.createServer();
const wss = new WebSocket.Server({ server });

server.listen(PORT, async () => {
  console.log(`WebSocket server listening on port ${PORT} (WS)`);
});

// Function to validate bearer token
function validateBearerToken(token) {
  return new Promise((resolve, reject) => {
    if (!token) {
      reject(new Error('No token provided'));
      return;
    }

    const urlObj = new URL(AUTH_API_URL);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || 443,
      path: urlObj.pathname,
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    };

    const req = https.request(options, (res) => {
      if (res.statusCode === 200) {
        resolve(true);
      } else {
        reject(new Error(`Authentication failed with status: ${res.statusCode}`));
      }
    });

    req.on('error', (error) => {
      reject(new Error(`Authentication request failed: ${error.message}`));
    });

    req.setTimeout(5000, () => {
      req.destroy();
      reject(new Error('Authentication request timeout'));
    });

    req.end();
  });
}

async function findPodByComposeId(composeId) {
  try {
    const response = await k8sApi.listNamespacedPod(
      NAMESPACE,
      undefined,
      undefined,
      undefined,
      undefined,
      `run_id=${composeId}`
    );
    
    if (response.body.items.length === 0) {
      throw new Error(`No pod found with label run_id=${composeId}`);
    }
    
    const pod = response.body.items[0];
    const podIP = pod.status.podIP;
    
    if (!podIP) {
      throw new Error(`Pod ${pod.metadata.name} does not have an IP address yet`);
    }
    
    console.log(`Found pod ${pod.metadata.name} with IP ${podIP} for compose_id=${composeId}`);
    return podIP;
  } catch (error) {
    console.error('Error finding pod:', error.message);
    throw error;
  }
}

wss.on('connection', async (ws, req) => {
  console.log('FE connected');
  
  // Parse query parameters
  const parsedUrl = url.parse(req.url, true);
  const composeId = parsedUrl.query.compose_id;
  const encodedToken = parsedUrl.query.token;
  
  if (!composeId) {
    console.error('Missing compose_id query parameter');
    ws.close(1008, 'Missing compose_id query parameter');
    return;
  }
  
  if (!encodedToken) {
    console.error('Missing token query parameter');
    ws.close(1008, 'Missing token query parameter');
    return;
  }
  
  // Decode the token (URL decode)
  let bearerToken;
  try {
    bearerToken = decodeURIComponent(encodedToken);
    console.log('Token decoded successfully');
  } catch (error) {
    console.error('Token decoding failed:', error.message);
    ws.close(1008, 'Invalid token encoding');
    return;
  }
  
  // Validate bearer token
  try {
    await validateBearerToken(bearerToken);
    console.log('Bearer token validated successfully');
  } catch (error) {
    console.error('Bearer token validation failed:', error.message);
    ws.close(1008, `Authentication failed: ${error.message}`);
    return;
  }
  
  console.log(`Received connection with compose_id=${composeId}`);
  
  try {
    // Find pod by compose_id label
    const podIP = await findPodByComposeId(composeId);
    
    // Connect to pod WebSocket using WS (not WSS) since it's private network
    // Don't include token in the connection to pod
    const backendWs = new WebSocket(`ws://${podIP}:8080?compose_id=${composeId}`);
    
    backendWs.on('open', () => {
      console.log(`Connected to pod at ${podIP} for run_id=${composeId}`);
    });
    
    backendWs.on('error', (error) => {
      console.error('Backend WebSocket error:', error.message);
      ws.close(1011, 'Backend connection error');
    });
    
    backendWs.on('message', (msg) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
      }
    });
    
    ws.on('message', (msg) => {
      if (backendWs.readyState === WebSocket.OPEN) {
        backendWs.send(msg);
      }
    });
    
    ws.on('close', () => {
      console.log('FE disconnected');
      backendWs.close();
    });
    
    backendWs.on('close', () => {
      console.log('Backend pod disconnected');
      ws.close();
    });
    
  } catch (error) {
    console.error(`Failed to connect to pod for compose_id=${composeId}:`, error.message);
    ws.close(1011, `Failed to find or connect to pod: ${error.message}`);
  }
});