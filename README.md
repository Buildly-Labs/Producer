# LOGIC Service

The Django Logic service is a template Logic Module for the Buildy RAD Core microservice architecture.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

What things you need to install the software and how to install them

You must have [Docker](https://www.docker.com/) installed.

### Build & run service locally

Build the Docker image:

```bash
docker-compose -f docker-compose.dev.yml build
```

Run a web server with this service:

```bash
docker-compose -f docker-compose.dev.yml up
```

Now, open your browser and go to [http://localhost:8080](http://localhost:8080).

For the admin panel, go to [http://localhost:8080/admin](http://localhost:8080/admin)
(user: `admin`, password: `admin`).

### Run tests

To run the tests once:

```bash
docker-compose -f docker-compose.dev.yml run --rm --entrypoint 'bash scripts/run-tests.sh' {name-of-service}
```

To run the tests and leave bash open inside the container so that it's possible to
re-run the tests faster again using `bash scripts/run-tests.sh [--keepdb]`:

```bash
docker-compose -f docker-compose.dev.yml run --rm --entrypoint 'bash scripts/run-tests.sh --bash-on-finish' {name-of-service}
```

To run bash:

```bash
docker-compose -f docker-compose.dev.yml run --rm --entrypoint 'bash' {name-of-service}
```

### Using GitHub Actions

This project uses GitHub Actions for CI/CD. The workflows are defined in the `.github/workflows` directory. Make sure your branch names match the deployment environments (e.g., `staging`, `production`).

### Requirements

For development builds, use `requirements-dev.txt`:

```bash
pip install -r requirements-dev.txt
```

For production builds, use `requirements-prod.txt`:

```bash
pip install -r requirements-prod.txt
```

## Deployment

Helm Charts for deployment to Digital Ocean, Google Cloud, and AWS can be found here: [HELM](https://github.com/buildlyio/helm-charts)

## Built With

* [GitHub Actions](https://github.com/features/actions) - CI/CD
* [TravisCI](http://www.travisci.org) - Recommended CI/CD

## Contributing

Please read [CONTRIBUTING.md](https://github.com/buildlyio/docs/CONTRIBUTING) for details on our code of conduct, and the process for submitting pull requests to us.

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/your/project/tags).

## Authors

* **Buildly** - *Initial work*

See also the list of [contributors](https://github.com/buildlyio/yourproject/contributors) who participated in this project.

## License

This project is licensed under the GPL v3 License - see the [LICENSE.md](LICENSE.md) file for details

## Acknowledgments

* Hat tip to anyone whose code was used
* Inspiration
* etc
