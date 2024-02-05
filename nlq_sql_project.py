import json
import os
import sqlite3
from time import time

from openai import OpenAI


def main():
    client = get_chat_client()

    db_path = get_path('nlq_db.sqlite')
    setup_path = get_path('setup.sql')
    setup_data_path = get_path('setupData.sql')

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    with (
        open(setup_path) as setup_file,
        open(setup_data_path) as setup_data_file
    ):
        setup_script = setup_file.read()
        setup_data_script = setup_data_file.read()

    cursor.executescript(setup_script)
    cursor.executescript(setup_data_script)

    common_request = '\n--- Using valid sqlite, answer the following questions for the tables provided above.\nQuestion: '
    strategies = {
        'zero_shot': setup_script + common_request,
        'double_shot': setup_script + common_request + "Who caught the most fish in Colorado?" +
                    "\nselect fisherman, name, count(*) from catch join person on catch.fisherman = person.person_id where state = 'CO' group by fisherman order by count(*) desc;" +
                    "\nQuestion: What is the average price of a store bought fly used to catch a fish?" +
                    "\nselect avg(price) from catch join fly on catch.fly = fly.fly_id where fly.homemade is false;" +
                    "\n Question: "
    }

    questions = [
        'What is the most caught fish species?',
        'Which fisherman has been most successful?',
        'Are there any anglers that tend to catch fish larger than average?',
        'Is there a brand of flies that does better at catching fish?',
        'What is the ratio of native to non-native fish caught?',
        'What time of day is best for catching fish?',
        'For anglers who use home tied flies, what is the ratio of fish released vs fish kept?',
        'Who caught the largest fish, what species, length, weight, and what fly was it on? Also, where and when did this happen?'
    ]

    for strategy in strategies:
        print('\n' + strategy)
        responses = {'strategy': strategy, 'prompt_prefix': strategies[strategy]}
        prompt_results = []
        for question in questions:
            print('\n' + question)
            error = 'None'
            try:
                sql_response = get_chat_response(strategies[strategy] + question + '\nselect', client)
                sql_response = sql_sanitize(sql_response)
                print(sql_response)

                query_result = str(run_query(sql_response, cursor))
                print(query_result)

                friendly_response_prompt = 'I asked this question: "' + question + '" and the response was "' + sql_response + '". After running this query, I got "' + query_result + '". Please give a concise, friendly response that simply answers the question for a user that asked the question but has no knowledge of SQL or the underlying database. Do not provide suggestions or other feedback.'
                friendly_response = get_chat_response(friendly_response_prompt, client)
                print(friendly_response)

                prompt_results.append({
                    'question': question,
                    'sql': sql_response,
                    'queryResult': query_result,
                    'friendlyResponse': friendly_response,
                    'error': error
                })
            except Exception as e:
                error = str(e)
                print(e)
                prompt_results.append({
                    'question': question,
                    'error': error
                })

        responses['questionResults'] = prompt_results
        with open(get_path(f'response_{strategy}_{time()}.json'), 'w') as output:
            json.dump(responses, output, indent=2)

    cursor.close()
    conn.close()

def get_path(filename):
    fdir = os.path.dirname(__file__)
    return os.path.join(fdir, filename)


def run_query(query, cursor):
    return cursor.execute(query).fetchall()


def get_chat_client():
    config_path = get_path('config.json')
    with open(config_path) as config_file:
        config = json.load(config_file)
    return OpenAI(
        api_key=config['openaiKey'],
        organization=config['orgId']
    )


def get_chat_response(content, client: OpenAI):
    stream = client.chat.completions.create(
        model='gpt-4-0125-preview',
        messages=[{'role': 'user', 'content': content}],
        stream=True
    )

    response_list = []
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            response_list.append(chunk.choices[0].delta.content)

    result = "".join(response_list)
    return result


def sql_sanitize(response):
    gpt_start_sql_marker = "```sql"
    gpt_end_sql_marker = "```"
    if gpt_start_sql_marker in response:
        response = response.split(gpt_start_sql_marker)[1]
    if gpt_end_sql_marker in response:
        response = response.split(gpt_end_sql_marker)[0]
    # if response.split(' ')[0].lower() != 'select':
    #     response = 'select ' + response

    return response


if __name__ == '__main__':
    main()
