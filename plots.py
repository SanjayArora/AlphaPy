##############################################################
#
# Package   : AlphaPy
# Module    : plots
# Version   : 1.0
# Copyright : Mark Conway
# Date      : July 15, 2015
#
##############################################################


#
# Model Plots
#
#     1. Calibration
#     2. Feature Importance
#     3. Learning Curve
#     4. ROC Curve
#     5. Confusion Matrix
#     6. Validation Curve
#
# EDA Plots
#
#     1. Scatter Plot Matrix
#     2. Facet Grid
#     3. Distribution Plot
#     4. Box Plot
#     5. Swarm Plot
#     6. Partial Dependence
#     7. Decision Boundary
#
# Time Series
#
#     1. Time Series
#     2. Candlestick
#

print(__doc__)


#
# Imports
#

from bokeh.plotting import figure, show, output_file
from estimators import ModelType
from globs import BSEP, PSEP, SSEP, USEP
from globs import Q1, Q3
from itertools import cycle
import logging
import math
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import pandas as pd
from scipy import interp
import seaborn as sns
from sklearn.calibration import calibration_curve
from sklearn.decomposition import PCA
from sklearn.ensemble.partial_dependence import partial_dependence
from sklearn.ensemble.partial_dependence import plot_partial_dependence
from sklearn.learning_curve import validation_curve
from sklearn.metrics import auc
from sklearn.metrics import confusion_matrix
from sklearn.metrics import roc_curve
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import learning_curve
from sklearn.model_selection import ShuffleSplit
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from util import remove_list_items


#
# Initialize logger
#

logger = logging.getLogger(__name__)


#
# Function get_partition_data
#

def get_partition_data(model, partition):
    """
    Get the X, y pair for a given model and partition
    """

    if partition == 'train':
        X = model.X_train
        y = model.y_train
    elif partition == 'test':
        X = model.X_test
        y = model.y_test
    else:
        raise TypeError('Partition must be train or test')

    return X, y


#
# Function generate_plots
#

def generate_plots(model, partition):
    """
    Save plot to a file.
    """

    logger.info("Generating Plots for Partition: %s", partition)

    # Extract model parameters

    calibration_plot = model.specs['calibration_plot']
    confusion_matrix = model.specs['confusion_matrix']
    importances = model.specs['importances']
    learning_curve = model.specs['learning_curve']
    roc_curve = model.specs['roc_curve']

    # Generate plots

    if calibration_plot:
        plot_calibration(model, partition)
    if confusion_matrix:
        plot_confusion_matrix(model, partition)
    if roc_curve:
        plot_roc_curve(model, partition)
    if partition == 'train':
        if importances:
            plot_importance(model, partition)
        if learning_curve:
            plot_learning_curve(model, partition)


#
# Function write_plot
#

def write_plot(model, vizlib, plot, plot_type, tag):
    """
    Save plot to a file.
    """

    # Extract model parameters

    base_dir = model.specs['base_dir']
    project = model.specs['project']

    # Create output file specification

    file_only = ''.join([plot_type, USEP, tag, '.png'])
    file_all = SSEP.join([base_dir, project, file_only])

    # Save plot

    logger.info("Writing plot to %s", file_all)

    if vizlib == 'matplotlib':
        plt.tight_layout()
        plt.savefig(file_all)
    elif vizlib == 'seaborn':
        plot.savefig(file_all)
    elif vizlib == 'bokeh':
        plot.save(file_all)
    elif vizlib == 'plotly':
        raise ValueError("Unsupported data visualization library: %s", vizlib)
    else:
        raise ValueError("Unrecognized data visualization library: %s", vizlib)


#
# Function plot_calibration
#

def plot_calibration(model, partition):
    """
    Display calibration plots

    Parameters
    ----------

    model : object that encapsulates all of the model parameters
    partition : 'train' or 'test'

    """

    logger.info("Generating Calibration Plot")

    # For classification only

    if model.specs['model_type'] != ModelType.classification:
        logger.info('Calibration plot is for classification only')
        return None

    # Get X, Y for correct partition

    X, y = get_partition_data(model, partition)

    # Excerpts from:
    #
    # Author: Jan Hendrik Metzen <jhm@informatik.uni-bremen.de>
    # License: BSD Style.

    plt.figure(figsize=(10, 10))
    ax1 = plt.subplot2grid((3, 1), (0, 0), rowspan=2)
    ax2 = plt.subplot2grid((3, 1), (2, 0))

    ax1.plot([0, 1], [0, 1], "k:", label="Perfectly Calibrated")
    for algo in model.algolist:
        logger.info("Calibration for Algorithm: %s", algo)
        clf = model.estimators[algo]
        if hasattr(clf, "predict_proba"):
            prob_pos = model.probas[(algo, partition)]
        else:  # use decision function
            prob_pos = clf.decision_function(X)
            prob_pos = \
                (prob_pos - prob_pos.min()) / (prob_pos.max() - prob_pos.min())
        fraction_of_positives, mean_predicted_value = \
            calibration_curve(y, prob_pos, n_bins=10)
        ax1.plot(mean_predicted_value, fraction_of_positives, "s-",
                 label="%s" % (algo, ))
        ax2.hist(prob_pos, range=(0, 1), bins=10, label=algo,
                 histtype="step", lw=2)

    ax1.set_ylabel("Fraction of Positives")
    ax1.set_ylim([-0.05, 1.05])
    ax1.legend(loc="lower right")
    ax1.set_title('Calibration Plots [Reliability Curve]')

    ax2.set_xlabel("Mean Predicted Value")
    ax2.set_ylabel("Count")
    ax2.legend(loc="upper center", ncol=2)

    write_plot(model, 'matplotlib', None, 'calibration', partition)


#
# Function plot_importances
#

def plot_importance(model, partition):
    """
    Display feature importances

    Parameters
    ----------

    model : object that encapsulates all of the model parameters
    partition : 'train' or 'test'

    """

    logger.info("Generating Feature Importance Plots")

    # Get X, Y for correct partition

    X, y = get_partition_data(model, partition)

    # For each algorithm that has importances, generate the plot.

    n_top = 10
    for algo in model.algolist:
        logger.info("Feature Importances for Algorithm: %s", algo)
        try:
            importances = model.importances[algo]
            # forest was input parameter
            indices = np.argsort(importances)[::-1]
            # log the feature ranking
            logger.info("Feature Ranking:")
            for f in range(n_top):
                logger.info("%d. Feature %d (%f)" % (f + 1, indices[f], importances[indices[f]]))
            # plot the feature importances
            title = BSEP.join([algo, "Feature Importances [", partition, "]"])
            plt.figure()
            plt.title(title)
            plt.bar(range(n_top), importances[indices][:n_top], color="b", align="center")
            plt.xticks(range(n_top), indices[:n_top])
            plt.xlim([-1, n_top])
            # save the plot
            tag = USEP.join([partition, algo])
            write_plot(model, 'matplotlib', None, 'feature_importance', tag)
        except:
            logger.info("%s does not have feature importances", algo)


#
# Function plot_learning_curve
#

def plot_learning_curve(model, partition):
    """
    Generate learning curves for a given partition.

    Parameters
    ----------

    model : object that encapsulates all of the model parameters
    partition : 'train' or 'test'

    """

    logger.info("Generating Learning Curves")

    # Extract model parameters.

    cv_folds = model.specs['cv_folds']
    n_jobs = model.specs['n_jobs']
    scorer = model.specs['scorer']
    seed = model.specs['seed']
    shuffle = model.specs['shuffle']
    split = model.specs['split']
    verbosity = model.specs['verbosity']

    # Get X, Y for correct partition.

    X, y = get_partition_data(model, partition)

    # Set cross-validation parameters to get mean train and test curves.

    cv = StratifiedShuffleSplit(n_splits=cv_folds, test_size=split,
                                random_state=seed)

    # Plot a learning curve for each algorithm.   

    ylim = (0.0, 1.01)
    train_sizes=np.linspace(.1, 1.0, 5)
    for algo in model.algolist:
        logger.info("Learning Curve for Algorithm: %s", algo)
        # get estimator
        estimator = model.estimators[algo]
        # plot learning curve
        title = BSEP.join([algo, "Learning Curve [", partition, "]"])
        # set up plot
        plt.figure()
        plt.title(title)
        if ylim is not None:
            plt.ylim(*ylim)
        plt.xlabel("Training Examples")
        plt.ylabel("Score")
        train_sizes, train_scores, test_scores = \
            learning_curve(estimator, X, y, train_sizes=train_sizes,
                           cv=cv, scoring=scorer, n_jobs=n_jobs,
                           verbose=verbosity)
        train_scores_mean = np.mean(train_scores, axis=1)
        train_scores_std = np.std(train_scores, axis=1)
        test_scores_mean = np.mean(test_scores, axis=1)
        test_scores_std = np.std(test_scores, axis=1)
        plt.grid()
        # plot data
        plt.fill_between(train_sizes, train_scores_mean - train_scores_std,
                         train_scores_mean + train_scores_std, alpha=0.1,
                         color="r")
        plt.fill_between(train_sizes, test_scores_mean - test_scores_std,
                         test_scores_mean + test_scores_std, alpha=0.1, color="g")
        plt.plot(train_sizes, train_scores_mean, 'o-', color="r",
                 label="Training Score")
        plt.plot(train_sizes, test_scores_mean, 'o-', color="g",
                 label="Cross-Validation Score")
        plt.legend(loc="best")
        # save the plot
        tag = USEP.join([partition, algo])
        write_plot(model, 'matplotlib', None, 'learning_curve', tag)


#
# Function plot_roc_curve
#

def plot_roc_curve(model, partition):
    """
    Display ROC Curves with Cross-Validation
    """

    logger.info("Generating ROC Curves")

    # For classification only

    if model.specs['model_type'] != ModelType.classification:
        logger.info('ROC Curves are for classification only')
        return None

    # Extract model parameters.

    cv_folds = model.specs['cv_folds']
    seed = model.specs['seed']
    shuffle = model.specs['shuffle']
    split = model.specs['split']

    # Get X, Y for correct partition.

    X, y = get_partition_data(model, partition)

    # Set up for stratified validation.

    if shuffle:
        cv = StratifiedShuffleSplit(n_splits=cv_folds, test_size=split,
                                    random_state=seed)
    else:
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=False,
                             random_state=seed)    

    # Plot a ROC Curve for each algorithm.

    for algo in model.algolist:
        logger.info("ROC Curve for Algorithm: %s", algo)
        # get estimator
        estimator = model.estimators[algo]
        # initialize true and false positive rates
        mean_tpr = 0.0
        mean_fpr = np.linspace(0, 1, 100)
        plt.figure()
        colors = cycle(['cyan', 'indigo', 'seagreen', 'yellow', 'blue', 'darkorange'])
        lw = 2
        # cross-validation
        i = 0
        for (train, test), color in zip(cv.split(X, y), colors):
            fold = i + 1
            logger.info("Cross-Validation Fold: %d of %d", fold, cv_folds)
            estimator.fit(X[train], y[train])
            probas_ = estimator.predict_proba(X[test])
            # compute ROC curve and area the curve
            fpr, tpr, thresholds = roc_curve(y[test], probas_[:, 1])
            mean_tpr += interp(mean_fpr, fpr, tpr)
            mean_tpr[0] = 0.0
            roc_auc = auc(fpr, tpr)
            plt.plot(fpr, tpr, lw=lw, label='ROC Fold %d (area = %0.2f)' % (fold, roc_auc))
            i += 1
        # plot mean ROC
        plt.plot([0, 1], [0, 1], linestyle='--', color='k', label='Luck')
        mean_tpr /= cv.get_n_splits(X, y)
        mean_tpr[-1] = 1.0
        mean_auc = auc(mean_fpr, mean_tpr)
        plt.plot(mean_fpr, mean_tpr, color='g', linestyle='--',
                 label='Mean ROC (area = %0.2f)' % mean_auc, lw=lw)
        # plot labels
        plt.xlim([-0.05, 1.05])
        plt.ylim([-0.05, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        title = BSEP.join([algo, "ROC Curve [", partition, "]"])
        plt.title(title)
        plt.legend(loc="lower right")
        # save chart
        tag = USEP.join([partition, algo])
        write_plot(model, 'matplotlib', None, 'roc_curve', tag)


#
# Function plot_confusion_matrix
#

def plot_confusion_matrix(model, partition):
    """
    Display the confusion matrix
    """

    logger.info("Generating Confusion Matrices")

    # Get X, Y for correct partition.

    X, y = get_partition_data(model, partition)

    for algo in model.algolist:
        logger.info("Confusion Matrix for Algorithm: %s", algo)
        # get predictions for this partition
        y_pred = model.preds[(algo, partition)]
        # compute confusion matrix
        cm = confusion_matrix(y, y_pred)
        logger.info('Confusion Matrix: %s', cm)
        # plot the confusion matrix
        np.set_printoptions(precision=2)
        plt.figure()
        cmap = plt.cm.Blues
        plt.imshow(cm, interpolation='nearest', cmap=cmap)
        title = BSEP.join([algo, "Confusion Matrix [", partition, "]"])
        plt.title(title)
        plt.colorbar()
        # set up x and y axes
        y_values, y_counts = np.unique(y, return_counts=True)
        tick_marks = np.arange(len(y_values))
        plt.xticks(tick_marks, y_values, rotation=45)
        plt.yticks(tick_marks, y_values)
        plt.tight_layout()
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        # save the chart
        tag = USEP.join([partition, algo])
        write_plot(model, 'matplotlib', None, 'confusion', tag)


#
# Function plot_validation_curve
#

def plot_validation_curve(model, partition, pname, prange):
    """
    Generate validation curves.

    Parameters
    ----------

    model : object that encapsulates all of the model parameters
    partition : data subset ['train' or 'test']
    pname : hyperparameter name ['gamma']
    prange : hyperparameter values [np.logspace(-6, -1, 5)]

    """

    logger.info("Generating Validation Curves")

    # Extract model parameters.

    cv_folds = model.specs['cv_folds']
    n_jobs = model.specs['n_jobs']
    scorer = model.specs['scorer']
    verbosity = model.specs['verbosity']

    # Get X, Y for correct partition.

    X, y = get_partition_data(model, partition)

    # Define plotting constants.

    spacing = 0.5
    alpha = 0.2

    # Calculate a validation curve for each algorithm.
    
    for algo in model.algolist:
        logger.info("Algorithm: %s", algo)
        # get estimator
        estimator = model.estimators[algo]
        # set up plot
        train_scores, test_scores = validation_curve(
            estimator, X, y, param_name=pname, param_range=prange,
            cv=cv_folds, scoring=scorer, n_jobs=n_jobs)
        train_scores_mean = np.mean(train_scores, axis=1)
        train_scores_std = np.std(train_scores, axis=1)
        test_scores_mean = np.mean(test_scores, axis=1)
        test_scores_std = np.std(test_scores, axis=1)
        # plot learning curves
        title = BSEP.join([algo, "Validation Curve [", partition, "]"])
        plt.title(title)
        # x-axis
        x_min, x_max = min(prange) - spacing, max(prange) + spacing
        plt.xlabel(pname)
        plt.xlim(x_min, x_max)
        # y-axis
        plt.ylabel("Score")
        plt.ylim(0.0, 1.1)
        # plot scores
        plt.plot(prange, train_scores_mean, label="Training Score", color="r")
        plt.fill_between(prange, train_scores_mean - train_scores_std,
                         train_scores_mean + train_scores_std, alpha=alpha, color="r")
        plt.plot(prange, test_scores_mean, label="Cross-Validation Score",
                 color="g")
        plt.fill_between(prange, test_scores_mean - test_scores_std,
                         test_scores_mean + test_scores_std, alpha=alpha, color="g")
        plt.legend(loc="best")        # save the plot
        tag = USEP.join([partition, algo])
        write_plot(model, 'matplotlib', None, 'validation_curve', tag)


#
# EDA Plots
#


#
# Function plot_scatter
#

def plot_scatter(model, data, features, target, tag='eda'):
    """
    Plot a scatterplot matrix
    """

    logger.info("Generating Scatter Plot")

    # Get the feature subset

    features.append(target)
    df = data[features]

    # Generate the pair plot

    sns.set()
    sns_plot = sns.pairplot(df, hue=target)

    # Save the plot

    write_plot(model, 'seaborn', sns_plot, 'scatter_plot', tag)


#
# Function plot_facet_grid
#

def plot_facet_grid(model, data, target, frow, fcol, tag='eda'):
    """
    Plot a Seaborn faceted histogram grid
    """

    logger.info("Generating Facet Grid")

    # Calculate the number of bins using the Freedman-Diaconis rule.

    tlen = len(data[target])
    tmax = data[target].max()
    tmin = data[target].min()
    trange = tmax - tmin
    iqr = data[target].quantile(Q3) - data[target].quantile(Q1)
    h = 2 * iqr * (tlen ** (-1/3))
    nbins = math.ceil(trange / h)

    # Generate the pair plot

    sns.set(style="darkgrid")

    fg = sns.FacetGrid(data, row=frow, col=fcol, margin_titles=True)
    bins = np.linspace(tmin, tmax, nbins)
    fg.map(plt.hist, target, color="steelblue", bins=bins, lw=0)

    # Save the plot

    write_plot(model, 'seaborn', fg, 'facet_grid', tag)


#
# Function plot_distribution
#

def plot_distribution(model, data, target, tag='eda'):
    """
    Distribution Plot
    """

    logger.info("Generating Distribution Plot")

    # Generate the distribution plot

    dist_plot = sns.distplot(data[target])
    dist_fig = dist_plot.get_figure()

    # Save the plot

    write_plot(model, 'seaborn', dist_fig, 'distribution_plot', tag)


#
# Function plot_box
#

def plot_box(model, data, x, y, hue, tag='eda'):
    """
    Box Plot
    """

    logger.info("Generating Box Plot")

    # Generate the box plot

    box_plot = sns.boxplot(x=x, y=y, hue=hue, data=data)
    sns.despine(offset=10, trim=True)
    box_fig = box_plot.get_figure()

    # Save the plot

    write_plot(model, 'seaborn', box_fig, 'box_plot', tag)


#
# Function plot_swarm
#

def plot_swarm(model, data, x, y, hue, tag='eda'):
    """
    Swarm Plot
    """

    logger.info("Generating Swarm Plot")

    # Generate the swarm plot

    swarm_plot = sns.swarmplot(x=x, y=y, hue=hue, data=data)
    swarm_fig = swarm_plot.get_figure()

    # Save the plot

    write_plot(model, 'seaborn', swarm_fig, 'swarm_plot', tag)


#
# Function plot_partial_dependence
#

def plot_partial_dependence(model, partition, targets):
    """
    Plot partial dependence
    """

    logger.info("Generating Partial Dependence Plot")

    # Get X, Y for correct partition

    X, y = get_partition_data(model, partition)

    # fetch California housing dataset
    cal_housing = fetch_california_housing()

    # split 80/20 train-test
    X_train, X_test, y_train, y_test = train_test_split(cal_housing.data,
                                                        cal_housing.target,
                                                        test_size=0.2,
                                                        random_state=1)
    names = cal_housing.feature_names

    print('_' * 80)
    print("Training GBRT...")
    clf = GradientBoostingRegressor(n_estimators=100, max_depth=4,
                                    learning_rate=0.1, loss='huber',
                                    random_state=1)
    clf.fit(X_train, y_train)
    print("done.")

    print('_' * 80)
    print('Convenience plot with ``partial_dependence_plots``')
    print

    features = [0, 5, 1, 2, (5, 1)]
    fig, axs = plot_partial_dependence(clf, X_train, features, feature_names=names,
                                       n_jobs=3, grid_resolution=50)
    fig.suptitle('Partial dependence of house value on nonlocation features\n'
                 'for the California housing dataset')
    plt.subplots_adjust(top=0.9)  # tight_layout causes overlap with suptitle

    print('_' * 80)
    print('Custom 3d plot via ``partial_dependence``')
    print
    fig = plt.figure()

    target_feature = (1, 5)
    pdp, (x_axis, y_axis) = partial_dependence(clf, target_feature,
                                               X=X_train, grid_resolution=50)
    XX, YY = np.meshgrid(x_axis, y_axis)
    Z = pdp.T.reshape(XX.shape).T
    ax = Axes3D(fig)
    surf = ax.plot_surface(XX, YY, Z, rstride=1, cstride=1, cmap=plt.cm.BuPu)
    ax.set_xlabel(names[target_feature[0]])
    ax.set_ylabel(names[target_feature[1]])
    ax.set_zlabel('Partial dependence')
    # pretty init view
    ax.view_init(elev=22, azim=122)
    plt.colorbar(surf)
    plt.suptitle('Partial dependence of house value on median age and '
                'average occupancy')
    plt.subplots_adjust(top=0.9)

    write_plot(model, 'matplotlib', None, 'partial_dependence', partition)


#
# Function plot_boundary
#

def plot_boundary(model, partition, f1, f2):
    """
    Display a comparison of classifiers
    """

    logger.info("Generating Boundary Plots")

    # For classification only

    if model.specs['model_type'] != ModelType.classification:
        logger.info('Boundary Plots are for classification only')
        return None

    # Get X, Y for correct partition

    X, y = get_partition_data(model, partition)

    # Define plotting constants.

    spacing = 0.5
    tspacing = 0.3
    # step size in the mesh
    h = .02

    xdim = 3 * (len(classifiers) + 1)
    ydim = xdim / len(classifiers)
    figure = plt.figure(figsize=(xdim, ydim))

    X, y = ds
    X = StandardScaler().fit_transform(X)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=.4)

    x_min, x_max = X[:, f1].min() - spacing, X[:, f1].max() + spacing
    y_min, y_max = X[:, f2].min() - spacing, X[:, f2].max() + spacing
    xx, yy = np.meshgrid(np.arange(x_min, x_max, h),
                         np.arange(y_min, y_max, h))

    # Plot the dataset first
    i = 1
    cm = plt.cm.RdBu
    cm_bright = ListedColormap(['#FF0000', '#0000FF'])
    ax = plt.subplot(1, len(classifiers) + 1, i)
    # Plot the training and testing points
    ax.scatter(X_train[:, 0], X_train[:, 1], c=y_train, cmap=cm_bright)
    ax.scatter(X_test[:, 0], X_test[:, 1], c=y_test, cmap=cm_bright, alpha=0.6)
    ax.set_xlim(xx.min(), xx.max())
    ax.set_ylim(yy.min(), yy.max())
    ax.set_xticks(())
    ax.set_yticks(())
    i += 1

    # iterate over classifiers
    for name, clf in zip(names, classifiers):
        ax = plt.subplot(1, len(classifiers) + 1, i)
        clf.fit(X_train, y_train)
        score = clf.score(X_test, y_test)

        # Plot the decision boundary. For that, we will assign a color to each
        # point in the mesh [x_min, m_max]x[y_min, y_max].

        if hasattr(clf, "decision_function"):
            Z = clf.decision_function(np.c_[xx.ravel(), yy.ravel()])
        else:
            Z = clf.predict_proba(np.c_[xx.ravel(), yy.ravel()])[:, 1]

        # Put the result into a color plot
        Z = Z.reshape(xx.shape)
        ax.contourf(xx, yy, Z, cmap=cm, alpha=.8)

        # Plot the training and testing points
        ax.scatter(X_train[:, 0], X_train[:, 1], c=y_train, cmap=cm_bright)
        ax.scatter(X_test[:, 0], X_test[:, 1], c=y_test, cmap=cm_bright,
                   alpha=0.6)

        ax.set_xlim(xx.min(), xx.max())
        ax.set_ylim(yy.min(), yy.max())
        ax.set_xticks(())
        ax.set_yticks(())
        ax.set_title(name)
        ax.text(xx.max() - tspacing, yy.min() + tspacing, ('%.2f' % score).lstrip('0'),
                size=15, horizontalalignment='right')
        i += 1

    figure.subplots_adjust(left=.02, right=.98)
    write_plot(model, 'matplotlib', None, 'boundary', partition)


#
# Time Series Plots
#


#
# Function plot_time_series
#

def plot_time_series(model, data, target, tag='eda'):
    """
    Time Series Plot
    """

    logger.info("Generating Time Series Plot")

    # Generate the time series plot

    ts_plot = sns.tsplot(data=data[target])
    ts_fig = ts_plot.get_figure()

    # Save the plot

    write_plot(model, 'seaborn', ts_fig, 'time_series_plot', tag)


#
# Function plot_candlestick
#

def plot_candlestick(df, symbol, cols=[], model=None):
    """
    Candlestick Charts
    """

    df["date"] = pd.to_datetime(df["date"])

    mids = (df.open + df.close) / 2
    spans = abs(df.close - df.open)

    inc = df.close > df.open
    dec = df.open > df.close
    w = 12 * 60 * 60 * 1000 # half day in ms

    TOOLS = "pan, wheel_zoom, box_zoom, reset, save"

    p = figure(x_axis_type="datetime", tools=TOOLS, plot_width=1000, toolbar_location="left")

    p.title = BSEP.join([symbol.upper(), "Candlestick"])
    p.xaxis.major_label_orientation = math.pi / 4
    p.grid.grid_line_alpha = 0.3

    p.segment(df.date, df.high, df.date, df.low, color="black")
    p.rect(df.date[inc], mids[inc], w, spans[inc], fill_color="#D5E1DD", line_color="black")
    p.rect(df.date[dec], mids[dec], w, spans[dec], fill_color="#F2583E", line_color="black")

    if model is not None:
        # save the plot
        write_plot(model, 'bokeh', p, 'candlestick_chart', symbol)
    else:
        show(p)
