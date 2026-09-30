import { Injectable, signal } from '@angular/core';
import { Subject, Observable, BehaviorSubject } from 'rxjs';
import { Client, IMessage, StompSubscription, IFrame } from '@stomp/stompjs';

export interface ProgressMessage {
  projectId: number;
  taskId: number;
  type: 'TASK_STARTED' | 'TASK_PROGRESS' | 'TASK_COMPLETED' | 'TASK_FAILED' | 'UPLOAD_PROGRESS' | 'PROCESSING_STATUS' | 'ANNOTATION_CREATED' | 'ANNOTATION_DELETED';
  progress: number;
  message: string;
  status: string;
  data?: any;
}

@Injectable({
  providedIn: 'root'
})
export class WebSocketService {
  private client: Client | null = null;
  private subscriptions = new Map<string, StompSubscription>();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  // State signals
  private connectionStatusSignal = signal<'connected' | 'connecting' | 'disconnected' | 'error'>('disconnected');
  connectionStatus = this.connectionStatusSignal.asReadonly();

  // Message subjects per project
  private projectMessagesMap = new Map<number, BehaviorSubject<ProgressMessage | null>>();
  
  // Global messages subject
  private messagesSubject = new Subject<ProgressMessage>();
  messages$ = this.messagesSubject.asObservable();

  private wsUrl = '';

  constructor() {
    // Determine WebSocket URL based on current location
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Connect to native WebSocket endpoint through nginx proxy
    this.wsUrl = `${wsProtocol}//${host}/ws/websocket`;
  }

  /**
   * Connect to the WebSocket server using STOMP over native WebSocket
   */
  connect(): void {
    if (this.client?.connected) {
      console.log('WebSocket already connected');
      return;
    }

    this.connectionStatusSignal.set('connecting');
    console.log('Connecting to WebSocket:', this.wsUrl);

    try {
      this.client = new Client({
        // Use native WebSocket - no SockJS dependency
        brokerURL: this.wsUrl,

        // Fase 5 (BFF): o CONNECT não leva token — o gateway troca o cookie da
        // sessão pelo access do drone no próprio upgrade, e o servidor o lê dali.

        // STOMP configuration
        reconnectDelay: 3000,
        heartbeatIncoming: 4000,
        heartbeatOutgoing: 4000,

        // Connection handlers
        onConnect: () => {
          console.log('STOMP connected');
          this.connectionStatusSignal.set('connected');
          this.reconnectAttempts = 0;
          
          // Resubscribe to all active projects
          this.projectMessagesMap.forEach((_, projectId) => {
            this.subscribeToProjectTopic(projectId);
          });
        },

        onStompError: (frame: IFrame) => {
          console.error('STOMP error:', frame.headers['message']);
          console.error('Details:', frame.body);
          this.connectionStatusSignal.set('error');
        },

        onWebSocketError: (error: Event) => {
          console.error('WebSocket error:', error);
          this.connectionStatusSignal.set('error');
        },

        onDisconnect: () => {
          console.log('STOMP disconnected');
          this.connectionStatusSignal.set('disconnected');
        }
      });

      this.client.activate();
    } catch (error) {
      console.error('Failed to create STOMP client:', error);
      this.connectionStatusSignal.set('error');
    }
  }

  /**
   * Disconnect from the WebSocket server
   */
  disconnect(): void {
    // Unsubscribe from all topics
    this.subscriptions.forEach((sub) => {
      try {
        sub.unsubscribe();
      } catch (e) {
        console.warn('Error unsubscribing:', e);
      }
    });
    this.subscriptions.clear();

    // Deactivate client
    if (this.client) {
      this.client.deactivate();
      this.client = null;
    }
    this.connectionStatusSignal.set('disconnected');
  }

  /**
   * Subscribe to progress updates for a specific project
   */
  subscribeToProject(projectId: number): Observable<ProgressMessage | null> {
    const subject = this.getProjectSubject(projectId);
    
    // Subscribe to topic if connected
    if (this.client?.connected) {
      this.subscribeToProjectTopic(projectId);
    }
    
    return subject.asObservable();
  }

  /**
   * Internal method to subscribe to a project topic
   */
  private subscribeToProjectTopic(projectId: number): void {
    const topic = `/topic/project/${projectId}/progress`;
    
    // Don't resubscribe if already subscribed
    if (this.subscriptions.has(topic)) {
      return;
    }

    if (this.client?.connected) {
      console.log(`Subscribing to topic: ${topic}`);
      const subscription = this.client.subscribe(topic, (message: IMessage) => {
        try {
          const body = JSON.parse(message.body) as ProgressMessage;
          console.log('STOMP message received:', body);
          
          // Emit to global stream
          this.messagesSubject.next(body);
          
          // Emit to project-specific stream
          const subject = this.getProjectSubject(projectId);
          subject.next(body);
        } catch (error) {
          console.error('Error parsing STOMP message:', error);
        }
      });
      
      this.subscriptions.set(topic, subscription);
    }
  }

  /**
   * Unsubscribe from a project
   */
  unsubscribeFromProject(projectId: number): void {
    const topic = `/topic/project/${projectId}/progress`;
    
    const subscription = this.subscriptions.get(topic);
    if (subscription) {
      try {
        subscription.unsubscribe();
      } catch (e) {
        console.warn('Error unsubscribing from topic:', e);
      }
      this.subscriptions.delete(topic);
    }
    
    // Clear the subject
    const subject = this.projectMessagesMap.get(projectId);
    if (subject) {
      subject.next(null);
    }
  }

  /**
   * Send a message to a destination
   */
  send(destination: string, body: any): void {
    if (this.client?.connected) {
      this.client.publish({
        destination,
        body: JSON.stringify(body)
      });
    } else {
      console.warn('STOMP is not connected. Message not sent:', body);
    }
  }

  /**
   * Get or create a BehaviorSubject for a project
   */
  private getProjectSubject(projectId: number): BehaviorSubject<ProgressMessage | null> {
    let subject = this.projectMessagesMap.get(projectId);
    if (!subject) {
      subject = new BehaviorSubject<ProgressMessage | null>(null);
      this.projectMessagesMap.set(projectId, subject);
    }
    return subject;
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.client?.connected ?? false;
  }
}
