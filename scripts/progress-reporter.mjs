/** Playwright reporter. The count is finished cases, from the test result, not the terminal text. */

export function nextProgress(state, event) {
  const finished = event.status === 'passed' || event.status === 'skipped' || event.retry >= event.retries;
  if (!finished) {
    const where = `${state.done} done of ${state.total}`;
    const line = event.retry
      ? `retry ${event.retry}  failed  ${event.title}  ${where}`
      : `failed  ${event.title}  ${where}`;
    return { done: state.done, line };
  }
  const done = state.done + 1;
  const count = `${done}/${state.total}`;
  if (event.status === 'passed') {
    const extra = event.retry ? `  on retry ${event.retry}` : '';
    return { done, line: `${count}  passed${extra}  ${event.title}` };
  }
  if (event.status === 'skipped') {
    return { done, line: `${count}  skipped  ${event.title}` };
  }
  const extra = event.retry ? `  after ${event.retry} retries` : '';
  return { done, line: `${count}  failed${extra}  ${event.title}` };
}

class ProgressReporter {
  constructor() {
    this.total = 0;
    this.done = 0;
  }

  printsToStdio() {
    return true;
  }

  onBegin(_config, suite) {
    this.total = suite.allTests().length;
    this.done = 0;
    process.stdout.write(`${this.total} tests\n`);
  }

  onTestEnd(test, result) {
    const path = test.titlePath();
    const title = path.length > 1 ? path.slice(1).join(' › ') : test.title;
    const step = nextProgress(
      { done: this.done, total: this.total },
      {
        title,
        status: result.status,
        retry: result.retry,
        retries: test.retries,
      },
    );
    this.done = step.done;
    process.stdout.write(`${step.line}\n`);
  }
}

export default ProgressReporter;
