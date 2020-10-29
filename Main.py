import os
import time
import neat

from Constraints import apply_constraints, apply_constraints_parallel
from NeatGenerator import NeatGenerator, create_population_lattices
from GeneticAlgorithm import GeneticAlgorithm
from Autoencoder import auto_encoder_2d, auto_encoder_3d, load_model, create_auto_encoder, add_noise_parallel
from Utility import calculate_error
from Visualization import plot_statistics, auto_encoder_plot
from Delenox_Config import *
import tensorflow as tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def sinc(x):
    x = max(-60.0, min(60.0, 5.0 * x))
    return (np.sin(x) + 1) / 2


if __name__ == '__main__':

    os.environ['TF_FORCE_GPU_ALLOW_GROWTH'] = 'true'
    physical_devices = tf.config.experimental.list_physical_devices('GPU')
    print(tf.test.is_gpu_available())
    assert len(physical_devices) > 0, "Not enough GPU hardware devices available"
    tf.config.experimental.set_memory_growth(physical_devices[0], True)

    # Load configuration file according to the given path and setting relevant parameters.
    local_dir = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'neat.cfg')
    config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet, neat.DefaultStagnation, config_path)
    config.__setattr__("pop_size", best_fit_count)
    config.genome_config.add_activation('sin_adjusted', sinc)

    k_means = []
    k_bests = []
    k_means_std = []
    k_bests_std = []

    encoder = load_model("cross_entropy_encoder_256")
    decoder = load_model("cross_entropy_decoder_256")

    neat_generator = NeatGenerator(
        encoder=encoder,
        decoder=decoder,
        config=config,
        generations=latent_generations,
        num_workers=thread_count,
        k=10,
        compressed_length=256
    )

    population, neat_means, neat_means_std, neat_bests, neat_bests_std = neat_generator.run_neat()
    k_bests.append(neat_bests)
    k_bests_std.append(neat_bests_std)
    k_means.append(neat_means)
    k_means_std.append(neat_means_std)

    plot_statistics(
        generations=latent_generations,
        bests=neat_bests,
        bests_confidence=neat_bests_std,
        means=neat_means,
        means_confidence=neat_means_std,
        names=["Neat"],
        averaged_runs=averaged_runs
    )

    """
    latent_solver_random = GeneticAlgorithm(
        n_genes=compressed_length,
        number_of_runs=averaged_runs,
        pop_size=best_fit_count,
        max_gen=latent_generations,
        mutation_rate=latent_mutation_rate,
        selection_strategy="roulette_wheel",
        variables_limits=latent_variable_range,
        k=10,
        plot_results=False,
        num_workers=thread_count
    )
    latent_means, latent_means_std, latent_bests, latent_bests_std = latent_solver_random.solve()
    """
