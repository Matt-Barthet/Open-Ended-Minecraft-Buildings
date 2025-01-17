# from conda import iteritems

from Generator.Autoencoder import add_noise, convert_to_integer, load_model, create_auto_encoder, auto_encoder_3d
from Generator.Constraints import *
from Generator.Delenox_Config import *
from Generator.Visualization import *


class NeatGenerator:
    """
    NEAT module of the Delenox pipeline, responsible for creating and evolving CPPN's which are
    used to generate lattices (genotype) that represent buildings (phenotype). Evolution uses
    novelty search as the heuristic, which computes the average Euclidean distance to the k-nearest
    neighbors as well as to an archive of unique novel individuals from past generations.
    """
    def __init__(self, config, population_id):
        self.experiment = ""
        self.population_id = population_id
        self.config = config
        self.config.__setattr__("pop_size", population_size)
        self.population = neat.Population(self.config)
        self.population.add_reporter(neat.StatisticsReporter())
        self.current_phase = 0
        self.current_gen = 0
        self.encoder = None
        self.decoder = None
        self.pool = None
        self.noise = False
        self.archive = []
        self.phase_best_fit = []
        self.archive_lattices = []
        self.neat_metrics = {'Experiment': None, 'Mean Novelty': [], 'Best Novelty': [], 'Node Complexity': [],
                             'Infeasible Size': [], 'Connection Complexity': [], 'Archive Size': [],
                             'Species Count': [], 'Mean Genetic Diversity': [],
                             'Minimum Species Size': [], 'Maximum Species Size': [], 'Mean Species Size': []}

    def run_neat(self, phase_number, p_experiment, static=False, noise=False, persistent_archive=True, train_on_archive=True):
        """
        Executes one "exploration" phase of the Delenox pipeline.  A set number of independent evolutionary runs
        are completed and the top N most novel individuals are taken and inserted into a population.  At the of
        the phase we look at the distribution of individuals in the population according to numerous metrics and
        statistics regarding the evolution of the populations such as the speciation, novelty scores etc.
        """
        # Check to see if we should clear the novelty archive before starting the next phase.
        if not persistent_archive:
            self.archive = []
            self.archive_lattices.clear()

        if phase_number == 0:
            self.config = load_config_file()
            self.__init__(self.config, self.population_id)

        # Re-initialize phase variables accordingly
        self.phase_best_fit.clear()
        self.current_gen = 0
        self.current_phase = phase_number
        self.experiment = p_experiment
        self.noise = noise

        # Load last phase's autoencoder, or the seed autoencoder if this is the first phase.
        if phase_number > 0 and static is False:
            self.encoder = load_model(
                "./Results/{}/Phase{:d}/encoder".format(p_experiment, phase_number - 1))
            self.decoder = load_model(
                "./Results/{}/Phase{:d}/decoder".format(p_experiment, phase_number - 1))
        else:
            # If the experiment uses a de-noising autoencoder, load the appropriate model.
            if not noise:
                self.encoder = load_model("./Results/Seed/encoder")
                self.decoder = load_model("./Results/Seed/decoder")
            else:
                self.encoder = load_model("./Results/Seed/encoder_noisy")
                self.decoder = load_model("./Results/Seed/decoder_noisy")

        # Update the archive of latent vectors with the current encoder's interpretation of the lattices
        self.archive = []
        for lattice in self.archive_lattices:
            self.archive.append(self.encoder.predict(lattice[None])[0])

        # Initialize the processes used for the NEAT run and execute the phase.
        self.pool = Pool(thread_count)
        self.population.run(self.run_one_generation, generations_per_run)
        self.pool.close()
        self.pool.join()

        # Update the NEAT metrics with the end-of-phase statistics.
        self.neat_metrics['Experiment'] = p_experiment
        self.neat_metrics['Mean Novelty'] = self.population.reporters.reporters[0].get_fitness_mean()
        self.neat_metrics['Best Novelty'] = self.population.reporters.reporters[0].get_fitness_stat(max)

        # Clearing the pool variable and auto-encoder as these cannot be saved to a pickle file.
        self.pool = None
        self.encoder = None
        self.decoder = None

        if train_on_archive:
            return self, self.archive_lattices, self.neat_metrics
        else:
            return self, self.phase_best_fit, self.neat_metrics

    def run_one_generation(self, genomes, config):
        """
        Multi-process fitness function for the NEAT module of the project.  Implements novelty search and
        scales the workload across the thread count given in the experiment parameters. Assigns a novelty
        value to each genome and keeps the feasible population separate, discarding and randomly regenerating
        the infeasible individuals.
        """
        start = time.time()
        compressed_population = {}
        lattices = {}
        remove = 0
        jobs = []

        for genome_id, genome in genomes:
            jobs.append(self.pool.apply_async(generate_lattice, (genome, config, False, None)))
        for job, (genome_id, genome) in zip(jobs, genomes):
            lattice, _, feasible = job.get()
            if not feasible:
                del self.population.population[genome_id]
                genome.fitness = 0
                remove += 1
            else:
                lattices.update({genome_id: lattice})

        for genome_id, lattice in lattices.items():
            to_compress = lattice
            if self.noise:
                to_compress = add_noise(lattice)
            compressed_population.update({genome_id: self.encoder.predict(to_compress[None])[0]})

        jobs.clear()
        for genome_id in compressed_population.keys():
            parameters = (compressed_population[genome_id], compressed_population, self.archive)
            jobs.append(self.pool.apply_async(novelty_search, parameters))
        for job, genome_id in zip(jobs, compressed_population.keys()):
            self.population.population[genome_id].fitness = job.get()

        fitness = {genome_id: fitness.fitness for genome_id, fitness in self.population.population.items() if
                   fitness.fitness > 0}
        sorted_keys = [k for k, _ in sorted(fitness.items(), key=lambda item: item[1])]

        for individual in range(1, np.min([add_to_archive, len(lattices)])):
            lattice = lattices[sorted_keys[-individual]]
            self.archive_lattices.append(lattice)
            vector = self.encoder.predict(lattice[None])[0]
            if len(self.archive) == 0 or not (vector == self.archive).all(1).any():
                self.archive.append(vector)

        if self.current_gen % 100 == 0 or self.current_gen + 1 == generations_per_run:
            most_novel_lattice = lattices[sorted_keys[-1]]
            least = lattices[sorted_keys[0]]
            mid = lattices[sorted_keys[int(len(sorted_keys) / 2)]]
            novelty_voxel_plot(
                [convert_to_integer(least), convert_to_integer(mid), convert_to_integer(most_novel_lattice)],
                self.current_gen + 1, self.population_id, self.current_phase, self.experiment)

        if self.current_gen + 1 == generations_per_run:
            np.savez_compressed("./Results/{}/Phase{:d}/Population_{:d}.npz".format(self.experiment, self.current_phase, self.population_id), lattices)
            for individual in range(1, np.min([best_fit_count, len(sorted_keys)])):
                self.phase_best_fit.append(lattices[sorted_keys[-individual]])

        node_complexity = 0
        connection_complexity = 0

        for individual in self.population.population.values():
            node_complexity += individual.size()[0]
            connection_complexity += individual.size()[1]

        node_complexity /= len(self.population.population)
        connection_complexity /= len(self.population.population)
        species_sizes = [len(specie.members) for specie in self.population.species.species.values() ]

        self.neat_metrics['Node Complexity'].append(node_complexity)
        self.neat_metrics['Connection Complexity'].append(connection_complexity)
        self.neat_metrics['Archive Size'].append(len(self.archive))
        self.neat_metrics['Species Count'].append(len(self.population.species.species))
        self.neat_metrics['Infeasible Size'].append(remove)
        self.neat_metrics['Minimum Species Size'].append(np.min(species_sizes))
        self.neat_metrics['Maximum Species Size'].append(np.max(species_sizes))
        self.neat_metrics['Mean Species Size'].append(np.mean(species_sizes))

        print("[Population {:d}]: Generation {:d} took {:2f} seconds.".format(self.population_id, self.current_gen, time.time() - start))
        print("Average Hidden Layer Size: {:2.2f}".format(node_complexity))
        print("Average Connection Count: {:2.2f}".format(connection_complexity))
        print("Size of the Novelty Archive: {:d}".format(len(self.archive)))
        print("Number of Infeasible Buildings:", remove)
        print("Number of Species:", len(self.population.species.species))
        print("Species Sizes:", species_sizes)
        print("Max Novelty:", fitness[sorted_keys[-1]])
        print("Mean Novelty:", np.mean(list(fitness.values())), "\n")

        current_compatibility = self.config.species_set_config.compatibility_threshold
        if len(self.population.species.species) < target_species_count:
            self.config.species_set_config.__setattr__("compatibility_threshold", current_compatibility - 0.05)
        elif len(self.population.species.species) > target_species_count:
            self.config.species_set_config.__setattr__("compatibility_threshold", current_compatibility + 0.05)

        self.current_gen += 1


def novelty_search(genome, compressed_population, archive):
    """
    Computes the novelty score for the given genome with respect to the current population and
    an archive of past novel individuals for this run. The score is the average euclidean distance
    to the nearest K neighbors (taken from the population and archive).
    :param genome: the ID of the genome being assessed.
    :param compressed_population: the population of latent vectors to compare to.
    :param archive: the archive of past novel individuals for this run.
    :return: the novelty score for this genome.
    """
    distances = []
    for neighbour in list(compressed_population.values()) + archive:
        distance = 0
        if (genome == neighbour).all():
            continue
        for element in range(len(neighbour)):
            distance += np.square(genome[element] - neighbour[element])
        distances.append(np.sqrt(distance))
    distances = np.sort(distances)
    return np.round(np.average(distances[:k_nearest_neighbors]), 2)


def generate_lattice(genome, config, noise_flag=True, plot=None):
    """
    Generates a lattice using the given CPPN genome and NEAT configuration file.  May also generate
    a noisy variant of the lattice (if a DAE is being used) and may plot the lattice if required.
    :param plot: Title of the figure for the plot
    :param noise_flag: Boolean value for adding noise.
    :param genome: CPPN object used to generate lattices.
    :param config: CPPN-NEAT config file specifying the parameters for the genomes.
    :return: generated lattice, noisy variant, feasibility status and
    """
    net = neat.nn.FeedForwardNetwork.create(genome, config)
    lattice = np.zeros(lattice_dimensions)
    noisy = np.zeros(lattice_dimensions)

    for (x, y, z) in value_range:
        lattice[x][y][z] = np.round(
            net.activate((x / lattice_dimensions[0], y / lattice_dimensions[0], z / lattice_dimensions[0]))[0])
    feasible, lattice = apply_constraints(lattice)
    if noise_flag:
        noisy = add_noise(lattice)
    if plot is not None:
        voxel_plot(lattice, plot)

    lattice = to_categorical(lattice, num_classes=5)
    noisy = to_categorical(noisy, num_classes=5)

    return np.asarray(lattice, dtype=bool), np.asarray(noisy, dtype=bool), feasible


def generate_lattices(genomes, config, noise_flag=True):
    pool = Pool(thread_count)
    jobs = []
    lattices = []
    noisy = []
    for genome in genomes:
        jobs.append(pool.apply_async(generate_lattice, (genome, config, noise_flag)))
    for job in jobs:
        lattice, noisy_lattice, valid = job.get()
        if valid:
            lattices.append(lattice)
            if noise_flag:
                noisy.append(noisy_lattice)
    pool.close()
    pool.join()
    return noisy, lattices


def create_population_lattices(config, noise_flag=True):
    """
    Generates a population of lattices and their noisy counterparts.
    :param noise_flag: boolean which determines whether a noised copy of the dataset should be created.
    :param config: CPPN-NEAT config file specifying the parameters for the genomes.
    :return lattices, noisy: the population of generated lattices and their noisy counterparts
    """
    lattices = []
    noisy = []
    while len(lattices) < best_fit_count * runs_per_phase:
        population = create_population(config, round((best_fit_count * runs_per_phase - len(lattices)) * 2))
        noisy_batch, lattice_batch = generate_lattices(population.population.values(), config, noise_flag)
        lattices += lattice_batch
        if noise_flag:
            noisy += noisy_batch
        print("{:d} Lattices created!".format(len(lattices)))
    return np.asarray(lattices[:1000], dtype=bool), np.asarray(noisy[:1000], dtype=bool)


def create_population(config, pop_size=population_size):
    """
    Generates a population of CPPN genomes according to the given CPPN-NEAT config file and population size.
    :param config: CPPN-NEAT config file specifying the parameters for the genomes.
    :param pop_size: Number of genomes to create.
    :return population: Population objecting containing a dictionary in the form {genome_id: genome_object}.
    """
    config.__setattr__("pop_size", pop_size)
    population = neat.Population(config)
    return population


def create_seed_files(config):
    """
    Initializes the NEAT populations which act as the seed for our experiments, and trains an auto-encoder
    on randomly initialized CPPNs to be used the first phase of the experiments.  This way all the experiments
    start with the same populations and the same auto-encoder eliminating potential randomness interfering with
    results.
    :param config: CPPN-NEAT config file specifying the parameters for the genomes.
    """
    training_population, _ = create_population_lattices(config, False)
    np.savez_compressed("Results/Seed/Initial_Training_Set.npz", np.asarray(training_population))
    _ = create_auto_encoder(model_type=auto_encoder_3d,
                            phase=-1,
                            population=np.asarray(training_population),
                            noisy=None,
                            experiment="Seed")
    for runs in range(runs_per_phase):
        generator = NeatGenerator(
            config=config,
            population_id=runs
        )
        with open("./Results/Seed/Neat_Population_{:d}.pkl".format(runs), "wb+") as f:
            pickle.dump(generator, f)


def load_config_file():
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'neat.cfg')
    config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                         neat.DefaultStagnation, config_path)
    config.genome_config.add_activation('sin_adjusted', sinc)
    return config


if __name__ == "__main__":

    config = load_config_file()

    pool = Pool(16)
    for pop in range(10):
        with open("../Generator/Results/Seed/Neat_Population_{:d}.pkl".format(pop), "rb") as file:
            generator = pickle.load(file)
        jobs = []
        lattices = []
        for genome_id, genome in list(iteritems(generator.population.population)):
            jobs.append(pool.apply_async(generate_lattice, (genome, config, False, None)))
        for job in jobs:
            result = job.get()
            if result[2]:
                lattices.append(result[0])
        np.save("../Generator/Results/Seed/Neat_Population_{:d}.npy".format(pop), lattices)
    pool.close()
    pool.join()


