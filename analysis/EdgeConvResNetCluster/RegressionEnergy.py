####################################################################################################
# ### ClassificationEdgeConvResNetCluster.py
#
# Example script for regression(Energy) training on the SiFi-CC data in graph configuration
#
####################################################################################################

import numpy as np
import os
import pickle as pkl
import json
import tensorflow as tf
import argparse

from spektral.layers import EdgeConv, GlobalMaxPool
from spektral.data.loaders import DisjointLoader

from SIFICCNN.utils.layers import ReZero
from SIFICCNN.datasets import DSGraphCluster
from SIFICCNN.models import SiFiECRNShort
from SIFICCNN.utils import parent_directory

from SIFICCNN.utils.plotter import plot_history_regression, plot_energy_error, \
    plot_energy_resolution


def main(run_name="ECRNCluster_unnamed",
         epochs=50,
         batch_size=64,
         dropout=0.1,
         nFilter=32,
         nOut=2,
         activation="relu",
         activation_out="relu",
         do_training=False,
         do_evaluation=False):
    # Train-Test-Split configuration
    trainsplit = 0.8
    valsplit = 0.2

    # create dictionary for model and training parameter
    modelParameter = {"nFilter": nFilter,
                      "activation": activation,
                      "n_out": nOut,
                      "activation_out": activation_out,
                      "dropout": dropout}

    # Datasets used
    # Training file used for classification and regression training
    # Generated via an input generator, contain one Bragg-peak position
    DATASET_CONT = "1to1_Cluster_CONT_2e10protons_simV3"
    DATASET_0MM = "1to1_Cluster_BP0mm_2e10protons_simV3"
    DATASET_5MM = "1to1_Cluster_BP5mm_4e9protons_simV3"
    DATASET_m5MM = "1to1_Cluster_BPm5mm_4e9protons_simV3"

    # go backwards in directory tree until the main repo directory is matched
    path = parent_directory()
    path_main = path
    path_results = path_main + "/results/" + run_name + "/"

    # create subdirectory for run output
    if not os.path.isdir(path_results):
        os.mkdir(path_results)
    for file in [DATASET_CONT, DATASET_0MM, DATASET_5MM, DATASET_m5MM]:
        if not os.path.isdir(path_results + "/" + file + "/"):
            os.mkdir(path_results + "/" + file + "/")

    # Both training and evaluation script are wrapped in methods to reduce memory usage
    # This guarantees that only one datasets is loaded into memory at the time
    if do_training:
        training(dataset_name=DATASET_CONT,
                 run_name=run_name,
                 trainsplit=trainsplit,
                 valsplit=valsplit,
                 batch_size=batch_size,
                 nEpochs=epochs,
                 path=path_results,
                 modelParameter=modelParameter)

    if do_evaluation:
        for file in [DATASET_0MM]:
            evaluate(dataset_name=file,
                     RUN_NAME=run_name,
                     path=path_results)


def training(dataset_name,
             run_name,
             trainsplit,
             valsplit,
             batch_size,
             nEpochs,
             path,
             modelParameter):
    # load graph datasets
    data = DSGraphCluster(name=dataset_name,
                          norm_x=None,
                          positives=True,
                          regression="Energy")

    # build tensorflow model
    tf_model = SiFiECRNShort(**modelParameter)
    print(tf_model.summary())

    # generate disjoint loader from datasets
    idx1 = int(trainsplit * len(data))
    idx2 = int((trainsplit + valsplit) * len(data))
    dataset_tr = data[:idx1]
    dataset_va = data[idx1:idx2]
    loader_train = DisjointLoader(dataset_tr,
                                  batch_size=batch_size,
                                  epochs=nEpochs)
    loader_valid = DisjointLoader(dataset_va,
                                  batch_size=batch_size)

    # Train model
    history = tf_model.fit(loader_train,
                           epochs=nEpochs,
                           steps_per_epoch=loader_train.steps_per_epoch,
                           validation_data=loader_valid,
                           validation_steps=loader_valid.steps_per_epoch,
                           verbose=1,
                           callbacks=[tf.keras.callbacks.ReduceLROnPlateau(monitor="val_loss",
                                                                           factor=1. / 3.,
                                                                           patience=4,
                                                                           min_delta=1e-2,
                                                                           min_lr=1e-6,
                                                                           verbose=0)])

    # Save everything after training process
    os.chdir(path)
    # save model
    print("Saving model at: ", run_name + "_regressionEnergy.tf")
    tf_model.save(run_name + "_regressionEnergy.tf")
    # save training history (not needed tbh)
    with open(run_name + "_regressionEnergy_history" + ".hst", 'wb') as f_hist:
        pkl.dump(history.history, f_hist)
    # save norm
    np.save(run_name + "_regressionEnergy" + "_norm_x", data.norm_x)
    # save model parameter as json
    with open(run_name + "_regressionEnergy_parameter.json", "w") as json_file:
        json.dump(modelParameter, json_file)

    # plot training history
    plot_history_regression(history.history, run_name + "_history_regressionEnergy")


def evaluate(dataset_name,
             RUN_NAME,
             path):
    # Change path to results directory to make sure the right model is loaded
    os.chdir(path)

    # load model, model parameter, norm, history
    with open(RUN_NAME + "_regressionEnergy_parameter.json", "r") as json_file:
        modelParameter = json.load(json_file)

    # load tensorflow model
    # Custom layers have to be stated to load accordingly
    tf_model = tf.keras.models.load_model(RUN_NAME + "_regressionEnergy.tf",
                                          custom_objects={"EdgeConv": EdgeConv,
                                                          "GlobalMaxPool": GlobalMaxPool,
                                                          "ReZero": ReZero})

    # load norm
    norm_x = np.load(RUN_NAME + "_regressionEnergy_norm_x.npy")

    # recompile model
    optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
    loss = "mean_absolute_error"
    list_metrics = ["mean_absolute_error"]
    tf_model.compile(optimizer=optimizer,
                     loss=loss,
                     metrics=list_metrics)

    # load model history and plot
    with open(RUN_NAME + "_regressionEnergy_history" + ".hst", 'rb') as f_hist:
        history = pkl.load(f_hist)
    plot_history_regression(history, RUN_NAME + "_history_regressionEnergy")

    # predict test datasets
    os.chdir(path + dataset_name + "/")

    # load datasets
    # Here all events are loaded and evaluated,
    # the true compton events are filtered later for plotting
    data = DSGraphCluster(name=dataset_name,
                          norm_x=norm_x,
                          positives=False,
                          regression="Energy")

    # Create disjoint loader for test datasets
    loader_test = DisjointLoader(data,
                                 batch_size=64,
                                 epochs=1,
                                 shuffle=False)

    # evaluation of test datasets (looks weird cause of bad tensorflow output format)
    y_true = []
    y_pred = []
    for batch in loader_test:
        inputs, target = batch
        p = tf_model(inputs, training=False)
        y_true.append(target)
        y_pred.append(p.numpy())
    y_true = np.vstack(y_true)
    y_pred = np.vstack(y_pred)
    y_true = np.reshape(y_true, newshape=(y_true.shape[0], 2))
    y_pred = np.reshape(y_pred, newshape=(y_pred.shape[0], 2))

    # export the classification results to a readable .txt file
    # .txt is used as it allowed to be accessible outside a python environment
    np.savetxt(fname=dataset_name + "_regE_pred.txt",
               X=y_pred,
               delimiter=",",
               newline="\n")

    labels = data.labels

    # evaluate model:
    plot_energy_error(y_pred[labels, :], y_true[labels, :], "error_regression_energy")
    # plot_energy_resolution(y_pred, y_true, "resolution_regression_energy")


if __name__ == "__main__":
    # configure argument parser
    parser = argparse.ArgumentParser(description='Trainings script ECRNCluster model')
    parser.add_argument("--name", type=str, help="Run name")
    parser.add_argument("--epochs", type=int, help="Number of epochs")
    parser.add_argument("--batch_size", type=int, help="Batch size")
    parser.add_argument("--dropout", type=float, help="Dropout")
    parser.add_argument("--nFilter", type=int, help="Number of filters per layer")
    parser.add_argument("--nOut", type=int, help="Number of output nodes")
    parser.add_argument("--activation", type=str, help="Activation function of layers")
    parser.add_argument("--activation_out", type=str, help="Activation function of output node")
    parser.add_argument("--training", type=bool, help="If true, do training process")
    parser.add_argument("--evaluation", type=bool, help="If true, do evaluation process")
    args = parser.parse_args()

    # this bunch is to set standard configuration if argument parser is not configured
    # looks ugly but works
    run_name = args.name if args.name is not None else "ECRNCluster_unnamed"
    epochs = args.epochs if args.epochs is not None else 50
    batch_size = args.batch_size if args.batch_size is not None else 64
    dropout = args.dropout if args.dropout is not None else 0.1
    nFilter = args.nFilter if args.nFilter is not None else 32
    nOut = args.nOut if args.nOut is not None else 2
    activation = args.activation if args.activation is not None else "relu"
    activation_out = args.activation_out if args.activation_out is not None else "relu"
    do_training = args.training if args.training is not None else False
    do_evaluation = args.evaluation if args.evaluation is not None else True

    main(run_name=run_name,
         epochs=epochs,
         batch_size=batch_size,
         dropout=dropout,
         nFilter=nFilter,
         nOut=nOut,
         activation=activation,
         activation_out=activation_out,
         do_training=do_training,
         do_evaluation=do_evaluation)
