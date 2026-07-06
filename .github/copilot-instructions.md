
> 📋 **Implementation Plan:** See [`PLAN.md`](./PLAN.md) for the finalized architecture decisions
> (TypeScript MFEs, single-spa parcels + SystemJS import-maps, uv/Python 3.12, nginx reverse proxy,
> chat via direct `astream` instead of Celery, `/tip/liveness` endpoint, docker-compose service list, etc.).
> Where this file and `PLAN.md` differ, **`PLAN.md` is authoritative**.

We are going to develop a monolithic application that is designed to expand into a microservices architecture in the future.
The application will be built using FastAPI in the backend and React in the frontend.
We will be using MicroFrontends architecture in the frontend. For the same, we shall use single SPA framework.
This whole application will be containerized using Docker and orchestrated using Docker compose for now.
In the future, we will be using Kubernetes for orchestration.
They will be deployed on AWS using ECS and ECR for container registry.
The domain address of this applicatoin is 'pragmatic-dev.in'.
This site is developed for the purpose of learning and development.

The site will handle two key functionalities
Feature 1: Mental health tip - 
a. when the user loads the site, it should initialzie sse connection and display a mental health tip from the backend
b. Also, it should make a liviness request to the backend every 30 seconds once so that the backend can trigger fresh mental health tip to the frontend.
c. The backend upon receiving the liviness request should update a redis cache and set the trigger to true
c. We use celery beat to trigger a langchain task via redis queue to generate a new mental health tip every 5 minutes. 
d. The task based on the trigger value in redis cache will generate a new mental health tip and update the redis cache with the new tip and set the trigger to false.
e. All the tips will come in the side panel of the site with 30% width of the screen and the main content will be in the remaining 70% width of the screen.
f. The tips stored in redis cache and it gets appended with newer one. We will maintain a maximum of 10 tips in the cache and older ones will be removed from the cache.
g. The backend endpoint will be /tip and it will return the latest tip from the redis cache.
i. The liviness endpoint will be /tip/liveness and it will return a 200 OK response with a message "liveness check successful" to the frontend.

Feature 2: Chat application
a. Takes remaining 70% width of the screen and will be a chat application where users can chat with the backend.
b. We stream the chat messages from the backend to the frontend using SSE connection.
c. The backend will trigger a celery task via redis queue. The task will run a langgraph workflow to generate a response to the user message and send it back to the frontend via SSE connection.
d. Currently, we will not be storing the chat messages in any database. The messages will be stored in the frontend state and will be lost when the user refreshes the page. In future, we will store the messages in a database.
e. For now, langgraph workflow will have only one task
f. The backend endpoint will be /chat

Future Enhancements:
1. We will add a database to store the chat messages and mental health tips.
2. We will add user authentication and authorization to the application. Create separate service to maintain user authentication and authorization.
3. Option to upload file and ask questions to the backend. The file will be indexed using metadata and stored in s3 bucket. Also chunked and stored in vector database. 
4. The backend will use langgraph to build the context using hybrid search and then make LLM call.


DO's:
1. For the backend, follow the FastAPI best practices and structure the code in a modular way.
2. For the frontend, follow the React best practices and structure the code in a modular way
3. Maintain env files for all the environment variables and secrets. Do not hardcode any secrets in the codebase.
4. Create a Readme.md file as well
5. Follow all Design patterns, SOLID principles and optimization techniques while developing the application.
6. For langchain, using LCEL pipeline. Keep the whole prompt, LLM  call and invoking separate step.
7. Follow strategy pattern for the choosing the LLM model to use for the prompt. The env variable will decide the model to use. 
8. For now, we will use openai gpt-4 model. The token shall be stored in the env variable. 

