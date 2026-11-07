package mqtt

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"
)

var (
	// ErrWorkerStopped indicates the worker pool is stopping or has stopped.
	ErrWorkerStopped = errors.New("worker pool stopped")
)

// IngestJob represents an asynchronous ingestion task.
type IngestJob struct {
	Req  IngestRequest
	Resp chan<- IngestJobResult
}

// IngestJobResult contains either the IngestResponse or an error.
type IngestJobResult struct {
	Response *IngestResponse
	Err      error
}

// BoundedWorkerPool processes IngestRequests concurrently with fixed workers and bounded queue.
type BoundedWorkerPool struct {
	handler     *JoinHelloIngestHandler
	queue       chan IngestJob
	workerCount int
	timeout     time.Duration
	wg          sync.WaitGroup
	ctx         context.Context
	cancel      context.CancelFunc
}

// NewBoundedWorkerPool initializes a worker pool with bounded capacity.
func NewBoundedWorkerPool(handler *JoinHelloIngestHandler, workerCount, queueCapacity int, timeout time.Duration) *BoundedWorkerPool {
	if workerCount <= 0 {
		workerCount = 4
	}
	if queueCapacity <= 0 {
		queueCapacity = 100
	}
	if timeout <= 0 {
		timeout = 5 * time.Second
	}

	ctx, cancel := context.WithCancel(context.Background())
	pool := &BoundedWorkerPool{
		handler:     handler,
		queue:       make(chan IngestJob, queueCapacity),
		workerCount: workerCount,
		timeout:     timeout,
		ctx:         ctx,
		cancel:      cancel,
	}

	pool.start()
	return pool
}

func (p *BoundedWorkerPool) start() {
	for i := 0; i < p.workerCount; i++ {
		p.wg.Add(1)
		go func() {
			defer p.wg.Done()
			for {
				select {
				case <-p.ctx.Done():
					return
				case job, ok := <-p.queue:
					if !ok {
						return
					}
					func() {
						defer func() {
							if r := recover(); r != nil {
								if job.Resp != nil {
									select {
									case job.Resp <- IngestJobResult{Err: fmt.Errorf("worker recovered from panic: %v", r)}:
									default:
									}
								}
							}
						}()
						jobCtx, jobCancel := context.WithTimeout(p.ctx, p.timeout)
						defer jobCancel()
						resp, err := p.handler.Handle(jobCtx, job.Req)
						if job.Resp != nil {
							select {
							case job.Resp <- IngestJobResult{Response: resp, Err: err}:
							default:
							}
						}
					}()
				}
			}
		}()
	}
}

// Enqueue submits an IngestRequest to the pool non-blockingly, failing closed if the queue is full.
func (p *BoundedWorkerPool) Enqueue(req IngestRequest, respChan chan<- IngestJobResult) error {
	select {
	case <-p.ctx.Done():
		return ErrWorkerStopped
	default:
	}

	job := IngestJob{
		Req:  req,
		Resp: respChan,
	}

	select {
	case p.queue <- job:
		return nil
	default:
		return ErrQueueFull
	}
}

// Stop gracefully stops all workers after draining or context cancellation.
func (p *BoundedWorkerPool) Stop() {
	p.cancel()
	p.wg.Wait()
}
