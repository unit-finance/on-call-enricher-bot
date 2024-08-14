import logging
import time
import urllib.parse
import requests
import cachetools
from robusta.api import *

cache_size = 100
lru_cache = cachetools.LRUCache(maxsize=cache_size)


class OnCallEnricherParams(ActionParams):
    """
    :var on_call_enricher_url: URL for the on-call enricher
    """
    on_call_enricher_url: str


class SearchParams(OnCallEnricherParams):
    """
    :var search_term: On-call enricher search term
    """
    search_term: str


@action
def show_on_call_search(event: ExecutionBaseEvent, params: SearchParams):
    """
    Add a finding with On-call enricher top results for the specified search term.
    This action can be used together with the stack_overflow_enricher.
    """

    logging.info(f"On-call enricher search term: {params.search_term}")

    answers = []
    try:
        if params.search_term in lru_cache:
            answers = lru_cache[params.search_term]
        else:
            start_time = time.time()
            url_with_param = f"{params.on_call_enricher_url}?{urllib.parse.urlencode({'search_term': params.search_term})}"
            response = requests.get(url_with_param)
            response.raise_for_status()  # Raises a HTTPError if the status is 4xx, 5xx

            if response:
                response_json = response.json()
                time_taken = time.time() - start_time
                logging.info(f"Response from on-call enricher: {response_json}")
                result = response_json.get('data', {}).get('result', '')
                lru_cache[params.search_term] = result  # Store the response in the cache
                answers.append(result)

            answers.append(f"\n\n ---")
            answers.append(f"\n\n | Time taken: {time_taken:.2f} seconds |")

    except Exception as e:
        answers.append(f"Error calling On-call enricher: {e}")
        raise

    finding = Finding(
        title=f"On-call enricher Results",
        source=FindingSource.PROMETHEUS,
        aggregation_key="On-call enricher Wisdom",
    )

    if answers:
        finding.add_enrichment([MarkdownBlock('\n'.join(answers))])
    else:
        finding.add_enrichment(
            [
                MarkdownBlock(
                    f'Sorry, On-call enricher doesn\'t know anything about "{params.search_term}"'
                )
            ]
        )
    event.add_finding(finding)


@action
def on_call_enricher(alert: PrometheusKubernetesAlert, params: OnCallEnricherParams):
    """
    Add a button to the alert - clicking it will ask on call enricher to help find a solution.
    """
    alert_name = alert.alert.labels.get("alertname", "")
    if not alert_name:
        return

    alert.add_enrichment(
        [
            CallbackBlock(
                {
                    f'Ask On-call enricher: {alert_name}': CallbackChoice(
                        action=show_on_call_search,
                        action_params=SearchParams(
                            search_term=f"{alert_name}",
                            on_call_enricher_url=params.on_call_enricher_url,
                        ),
                    )
                },
            )
        ]
    )
