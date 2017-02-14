import numpy as np
import tensorflow as tf

import cPickle
import os
import time
import json
import cPickle

from utilities import train_data_iterator

class Config(object):

    def __init__(self):
        self.dropout = 0.5
        self.embed_dim = 50
        self.hidden_dim = 200
        self.batch_size = 256
        self.no_of_epochs = 10
        self.lr = 0.001
        self.img_dim = 2048
        self.vocab_size = 10000
        self.no_of_layers = 1
        self.max_no_of_epochs = 10
        self.model_name = "model_keep=%.2f_batch=%d_hidden_dim=%d_embed_dim=%d_layers=%d" % (self.dropout,
                    self.batch_size, self.hidden_dim, self.embed_dim,
                    self.no_of_layers)

class Model(object):

    def __init__(self, config, GloVe_embeddings):
        self.GloVe_embeddings = GloVe_embeddings
        self.config = config
        self.load_utilities_data()
        self.add_placeholders()
        self.add_input()
        self.add_logits()
        self.add_loss_op()
        self.add_training_op()

    def load_utilities_data(self):
        self.vocabulary = cPickle.load(open("coco/data/vocabulary"))

    def add_placeholders(self):
        self.captions_ph = tf.placeholder(tf.int32,
                    shape=[None, None],
                    name="captions_ph")
        self.imgs_ph = tf.placeholder(tf.float32,
                    shape=[None, self.config.img_dim],
                    name="imgs_ph")
        self.labels_ph = tf.placeholder(tf.int32,
                    shape=[None, None],
                    name="labels_ph")
        self.dropout_ph = tf.placholder(tf.float32, name="dropout_ph")

    def create_feed_dict(self, captions_batch, imgs_batch, labels_batch=None, dropout=1):
        feed_dict = {}
        feed_dict[self.captions_ph] = captions_batch
        feed_dict[self.imgs_ph] = imgs_batch
        feed_dict[self.dropout_ph] = dropout
        if labels_batch is not None:
            feed_dict[self.labels_ph] = labels_batch

        return feed_dict

    def add_input(self):
        with tf.variable_scope("img_transform"):
            W_img = tf.get_variable("W_img",
                        shape=[self.config.img_dim, self.config.embed_dim])
            b_img = tf.get_variable("b_img", shape=[self.config.embed_dim])
            imgs_input = tf.nn.sigmoid(tf.matmul(self.imgs_ph, W_img) + b_img)
            imgs_input = tf.expand_dims(imgs_input, 1)

        with tf.variable_scope("captions_embed"):
            word_embeddings = tf.get_variable("word_embeddings",
                        self.GloVe_embeddings)
            captions_input = tf.nn.embedding_lookup(word_embeddings,
                        self.captions_ph)

        self.input = tf.concat(1, [imgs_input, captions_input])

    def add_logits(self):
        LSTM = tf.nn.rnn_cell.BasicLSTMCell(self.config.hiddem_dim,
                    input_size=self.config.embed_dim)
        LSTM_dropout = tf.nn.rnn_cell.DropoutWrapper(LSTM,
                    input_keep_prob=self.dropout_ph,
                    output_keep_prob=self.dropout_ph)
        multilayer_LSTM = tf.nn.rnn_cell.MultiRNNCell(
                    [LSTM_dropout]*self.config.no_of_layers)
        initial_state = multilayer_LSTM.zero_state(self.config.batch_size,
                    tf.float32)
        outputs, final_state = tf.nn.dynamic_rnn(multilayer_LSTM,
                    self.input, initial_state=initial_state)
        output = tf.reshape(outputs, [-1, self.config.hidden_dim])

        with tf.variable_scope("logits"):
            W_logits = tf.get_variable("W_logits",
                        shape=[self.config.hidden_dim, self.config.vocab_size])
            b_logits = tf.get_variable("b_logits",
                        shape=[self.config.vocab_size])
            self.logits = tf.matmul(output, W_logits) + b_logits

    def add_loss_op(self):
        labels = tf.reshape(self.labels_ph, [-1])
        loss_per_word = tf.nn.sparse_softmax_cross_entropy_with_logits(
                    self.logits, labels)
        loss = tf.reduce_mean(loss_per_word)

        self.loss = loss

    def add_training_op(self):
        optimizer = tf.train.AdamOptimizer(learning_rate=self.config.lr)
        self.train_op = optimizer.minimize(self.loss)

    def run_epoch(self, session):
        batch_losses = []
        start_time = time.time()

        for step, (captions, imgs, labels) in enumerate(train_data_iterator(self.config)):
            feed_dict = self.create_feed_dict(captions, imgs, labels_batch=labels,
                        dropout=self.config.dropout)
            batch_loss, _ = session.run([self.loss, self.train_op],
                        feed_dict=feed_dict)
            batch_losses.append(batch_loss)

        return batch_losses

    def generate_img_caption(self, session, img_vector, vocabulary):
        caption = np.array([vocabulary.index("<SOS>")])
        prediciton_index = 1

        while caption[-1] is not vocabulary.index("<EOS>"):
            feed_dict = self.create_feed_dict(caption, img_vector)
            logits = session.run([self.logits], feed_dict=feed_dict)
            prediction_logits = logits[prediction_index, :]
            prediciton = np.argmax(prediction_logits)
            prediciton_index += 1

def main(debug=False):
    config = Config()
    GloVe_embeddings = cPickle.load(open("coco/data/embeddings_matrix"))
    model = Model(config, GloVe_embeddings)

    epoch_losses = []
    all_results_json = {}

    init = tf.initialize_all_variables()
    saver = tf.train.Saver()

    with tf.Session() as sess:
        sess.run(init)
        for epoch in range(config.max_no_of_epochs):
            batch_losses = model.run_epoch(sess)
            epoch_loss = np.mean(batch_losses)
            epoch_losses.append(epoch_loss)

            if not os.path.exists(config.model_name):
                os.mkdir(config.model_name)
            if not os.path.exists("%s/weights" % config.model_name):
                os.mkdir("%/weights" % config.model_name)
            saver.save(sess, "%s/weights/model" % config.model_name,
                    global_step=epoch)

            if not os.path.exists("%s/loss" % config.model_name):
                os.mkdir("%s/loss" %config.model_name)
            cPickle.dump(epoch_losses, open("%s/loss/epoch_losses" % config.model_name, "w"))

            generate_captions_val(sess, model, epoch)
            results_file = "%s/results/val_res_%d.json" %(config.model_name,
                    epoch)
            results = evaluateModel(results_file)
            all_results_json[epoch] = results

            with open("%s/results/evaluation_val.json" % config.model_name, 'w') as file:
                json.dump(all_results_json, file, sort_keys=True, indent=4)

if __name__ == '__main__':
    main()
